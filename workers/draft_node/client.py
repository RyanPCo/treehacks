"""
Draft Node - DraftNodeService Implementation
Generates draft tokens and coordinates with Modal verification service.
"""
import modal
import sys
import os
import threading
from vllm import LLM, SamplingParams
import time
from dataclasses import dataclass

# Add proto directory to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'proto'))

import common_pb2
import speculative_decoding_pb2


@dataclass
class Token:
    token_id: int
    text: str
    logprob: float


class _VerifyResult:
    """Thread-safe container for async verification result."""
    def __init__(self, handle):
        self.handle = handle
        self.result = None
        self.ready = threading.Event()
        self._thread = threading.Thread(target=self._wait, daemon=True)
        self._thread.start()

    def _wait(self):
        self.result = self.handle.get()
        self.ready.set()

    def poll(self):
        """Non-blocking check. Returns result if ready, else None."""
        if self.ready.is_set():
            return self.result
        return None

    def get(self):
        """Blocking wait."""
        self.ready.wait()
        return self.result


class DraftNodeClient:
    def __init__(
        self,
        draft_model="Qwen/Qwen2.5-0.5B-Instruct",
        num_draft_tokens=5,
        num_candidates=1,
        candidate_temperature=0.0,
        candidate_top_p=0.9,
        optimistic_prefill=True,
        modal_app_name="treehacks-verification-service",
        modal_class_name="VerificationService",
    ):
        print(f"Initializing draft node with model: {draft_model}")
        self.llm = LLM(
            model=draft_model,
            gpu_memory_utilization=0.9,
            max_model_len=4096,
            enable_prefix_caching=True,
        )

        self.num_draft_tokens = num_draft_tokens
        self.num_candidates = num_candidates
        self.candidate_temperature = candidate_temperature
        self.candidate_top_p = candidate_top_p
        self.optimistic_prefill = optimistic_prefill

        # Multi-candidate statistics
        self.candidate_win_counts = [0] * num_candidates
        self.per_round_acceptance_lengths = []

        # Optimistic prefill statistics
        self._optimistic_hits = 0
        self._optimistic_misses = 0

        from transformers import AutoTokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(draft_model)

        # Cache EOS token IDs (Qwen has <|endoftext|> and <|im_end|>, etc.)
        self.eos_token_ids = set()
        if getattr(self.tokenizer, 'eos_token_id', None) is not None:
            self.eos_token_ids.add(self.tokenizer.eos_token_id)
        vocab = self.tokenizer.get_vocab()
        for token in ("<|endoftext|>", "<|im_end|>"):
            if token in vocab:
                self.eos_token_ids.add(self.tokenizer.convert_tokens_to_ids(token))

        # Connect to Modal verification service
        print("Connecting to Modal verification service...")
        self.verification_service = modal.Cls.from_name(
            modal_app_name, modal_class_name
        )()

        print(f"Draft node ready! (num_candidates={num_candidates}, optimistic_prefill={optimistic_prefill})")

    def _pick_best_candidate(self, candidates):
        """Returns index of candidate with highest sum of draft logprobs."""
        best_idx = 0
        best_score = float('-inf')
        for i, c in enumerate(candidates):
            score = sum(c['draft_logprobs']) if c['draft_logprobs'] else float('-inf')
            if score > best_score:
                best_score = score
                best_idx = i
        return best_idx

    def _spawn_verification(self, request, prefix_ids, candidates, active_n):
        """Fire verification via .spawn() (non-blocking). Returns a handle."""
        if active_n > 1:
            return self.verification_service.verify_multi_candidate.spawn(
                request_id=request.request_id,
                session_id="session-0",
                prefix_token_ids=list(prefix_ids),
                candidates=candidates,
                temperature=request.params.temperature if request.params.temperature > 0 else 0.8,
                top_k=request.params.top_k if request.params.top_k > 0 else -1,
            )
        else:
            return self.verification_service.verify_draft.spawn(
                request_id=request.request_id,
                session_id="session-0",
                prefix_token_ids=list(prefix_ids),
                draft_token_ids=list(candidates[0]['draft_token_ids']),
                draft_logprobs=list(candidates[0]['draft_logprobs']),
                temperature=request.params.temperature if request.params.temperature > 0 else 0.8,
                top_k=request.params.top_k if request.params.top_k > 0 else -1,
            )

    def execute_inference_stream(self, request):
        """
        Execute inference with speculative decoding and stream round events.

        Args:
            request: InferenceJobRequest

        Returns:
            Yields tuples of:
            - ("round", round_event_dict, token_event_dicts)
            - ("done", InferenceJobResponse, [])
        """
        start_time = time.time()

        current_token_ids = self.tokenizer.encode(request.prompt)
        all_tokens = []

        # Statistics
        total_draft_generated = 0
        total_draft_accepted = 0
        speculation_rounds = 0

        # Per-round timing arrays
        timing_draft_ms = []
        timing_verify_ms = []
        timing_process_ms = []
        timing_optimistic_ms = []

        max_tokens = request.params.max_tokens if request.params.max_tokens > 0 else 16
        draft_tokens_per_round = request.params.draft_tokens if request.params.draft_tokens > 0 else self.num_draft_tokens

        eos_token_ids = self.eos_token_ids
        REPEAT_WINDOW = 6  # stop if last N tokens are all the same

        print(f"\n{'='*80}")
        print(f"Starting inference for request: {request.request_id}")
        print(f"   Prompt: {request.prompt!r}")
        print(f"   Max tokens: {max_tokens}")
        print(f"   Draft tokens/round: {draft_tokens_per_round}")
        print(f"   Num candidates: {self.num_candidates}")
        print(f"   Optimistic prefill: {self.optimistic_prefill}")
        print(f"{'='*80}\n")

        # Optimistic prefill state
        pending_verify = None          # _VerifyResult instance
        pending_candidates = None      # candidates sent for verification
        pending_active_n = None
        pending_bet_idx = None         # which candidate we bet on
        pending_spawn_time = None      # when .spawn() was called
        optimistic_tokens = []         # optimistic token ids generated during poll
        bet_hit = False                # whether the last bet was correct

        while len(all_tokens) < max_tokens:
            speculation_rounds += 1

            # ── Step A: Process previous round's verification result ──
            eos_reached = False
            if pending_verify is not None:
                verify_result_raw = pending_verify.get()
                timing_verify_ms.append(verify_result_raw.get("verification_time_ms", 0.0))

                process_start = time.time()

                prev_candidates = pending_candidates
                prev_active_n = pending_active_n

                if prev_active_n > 1:
                    verify_response = verify_result_raw
                    best_idx = verify_response["best_candidate_idx"]
                    best_result = verify_response["candidate_results"][best_idx]
                    num_accepted = best_result["num_accepted"]
                    best_draft = prev_candidates[best_idx]['draft_token_ids']

                    accepted_lengths = [r["num_accepted"] for r in verify_response["candidate_results"]]
                    self.per_round_acceptance_lengths.append(accepted_lengths)
                    print(f"    Accepted lengths: {accepted_lengths}, best_idx={best_idx}")

                    if best_idx < len(self.candidate_win_counts):
                        self.candidate_win_counts[best_idx] += 1

                    total_draft_generated += len(best_draft)
                    total_draft_accepted += num_accepted

                    verify_result = {
                        "num_accepted_tokens": num_accepted,
                        "acceptance_mask": best_result["acceptance_mask"],
                        "corrected_token_ids": best_result["corrected_token_ids"],
                        "corrected_logprobs": best_result["corrected_logprobs"],
                        "next_token_id": best_result["next_token_id"],
                        "next_token_logprob": best_result["next_token_logprob"],
                    }
                else:
                    verify_result = verify_result_raw
                    best_idx = 0
                    best_draft = prev_candidates[0]['draft_token_ids']
                    num_accepted = verify_result["num_accepted_tokens"]
                    total_draft_generated += len(best_draft)
                    total_draft_accepted += num_accepted

                acceptance_rate_round = num_accepted / len(best_draft) if best_draft else 0.0
                print(f"    Verified: {num_accepted}/{len(best_draft)} accepted ({acceptance_rate_round:.1%})")

                # Check if bet paid off
                bet_hit = False
                if self.optimistic_prefill and pending_bet_idx is not None:
                    if prev_active_n > 1:
                        # Multi-candidate: bet wins if best_idx matches and fully accepted
                        bet_hit = (best_idx == pending_bet_idx and num_accepted == len(best_draft))
                    else:
                        # Single candidate: bet wins if fully accepted with no corrections
                        bet_hit = (num_accepted == len(best_draft) and not verify_result["corrected_token_ids"])

                    if bet_hit and optimistic_tokens:
                        self._optimistic_hits += 1
                        print(f"    Optimistic prefill HIT! ({len(optimistic_tokens)} tokens saved)")
                    else:
                        if pending_bet_idx is not None:
                            self._optimistic_misses += 1
                            if optimistic_tokens:
                                print(f"    Optimistic prefill MISS (discarding {len(optimistic_tokens)} tokens)")
                            else:
                                print(f"    Optimistic prefill MISS (0 tokens generated)")
                        optimistic_tokens = []

                round_token_events = []

                # Accept the verified tokens
                accepted_tokens = best_draft[:num_accepted]
                current_token_ids.extend(accepted_tokens)

                for token_id in accepted_tokens:
                    round_token_events.append({
                        "text": self.tokenizer.decode([token_id]),
                        "type": "accepted",
                        "token_id": token_id,
                        "logprob": 0.0,
                    })

                if num_accepted < len(best_draft):
                    rejected_token_id = best_draft[num_accepted]
                    round_token_events.append({
                        "text": self.tokenizer.decode([rejected_token_id]),
                        "type": "rejected",
                        "token_id": rejected_token_id,
                        "logprob": 0.0,
                    })

                # Add corrected token if any
                if verify_result["corrected_token_ids"]:
                    current_token_ids.extend(verify_result["corrected_token_ids"])
                    print(f"    Corrected: +{len(verify_result['corrected_token_ids'])} tokens from target")
                    for i, token_id in enumerate(verify_result["corrected_token_ids"]):
                        corrected_logprobs = verify_result["corrected_logprobs"]
                        round_token_events.append({
                            "text": self.tokenizer.decode([token_id]),
                            "type": "corrected",
                            "token_id": token_id,
                            "logprob": corrected_logprobs[i] if i < len(corrected_logprobs) else 0.0,
                        })

                # Add to result
                for token_id in accepted_tokens:
                    token = Token(
                        token_id=token_id,
                        text=self.tokenizer.decode([token_id]),
                        logprob=0.0,
                    )
                    all_tokens.append(token)
                    if eos_token_ids and token_id in eos_token_ids:
                        eos_reached = True
                        break

                if not eos_reached:
                    for i, token_id in enumerate(verify_result["corrected_token_ids"]):
                        corrected_logprobs = verify_result["corrected_logprobs"]
                        token = Token(
                            token_id=token_id,
                            text=self.tokenizer.decode([token_id]),
                            logprob=corrected_logprobs[i] if i < len(corrected_logprobs) else 0.0,
                        )
                        all_tokens.append(token)
                        if eos_token_ids and token_id in eos_token_ids:
                            eos_reached = True
                            break

                # Check next_token_id from target (when all draft tokens accepted)
                if not eos_reached and eos_token_ids and verify_result["next_token_id"] in eos_token_ids:
                    token = Token(
                        token_id=verify_result["next_token_id"],
                        text=self.tokenizer.decode([verify_result["next_token_id"]]),
                        logprob=verify_result["next_token_logprob"] or 0.0,
                    )
                    all_tokens.append(token)
                    current_token_ids.append(verify_result["next_token_id"])
                    eos_reached = True

                # Check for repetition loop
                if not eos_reached and len(all_tokens) >= REPEAT_WINDOW:
                    last_ids = [t.token_id for t in all_tokens[-REPEAT_WINDOW:]]
                    if len(set(last_ids)) == 1:
                        print(f"    Repetition detected (token {last_ids[0]} repeated {REPEAT_WINDOW}x), ending generation")
                        eos_reached = True
                    round_token_events.append({
                        "text": token.text,
                        "type": "accepted",
                        "token_id": token.token_id,
                        "logprob": token.logprob,
                    })

                if eos_reached:
                    if eos_token_ids:
                        eos_idx = next((i for i, tid in enumerate(current_token_ids) if tid in eos_token_ids), None)
                        if eos_idx is not None:
                            current_token_ids = current_token_ids[:eos_idx + 1]
                    print(f"    EOS token reached, ending generation")

                    process_time = (time.time() - process_start) * 1000
                    timing_process_ms.append(process_time)
                    break

                process_time = (time.time() - process_start) * 1000
                timing_process_ms.append(process_time)

                # Yield round event (we have verification data from Step A)
                round_event = {
                    "round_num": speculation_rounds,
                    "drafted": len(best_draft),
                    "accepted": num_accepted,
                    "corrected": len(verify_result["corrected_token_ids"]),
                    "verification_time_ms": float(verify_result_raw.get("verification_time_ms", 0.0)),
                    "acceptance_rate": float(verify_result_raw.get("acceptance_rate", acceptance_rate_round)),
                }
                yield ("round", round_event, round_token_events)

                # Reset pending state
                pending_verify = None
                pending_candidates = None
                pending_active_n = None
                pending_bet_idx = None
                pending_spawn_time = None

            # Check if max tokens reached after processing verification
            if len(all_tokens) >= max_tokens:
                break

            # ── Step B: Generate draft candidates ──
            num_to_draft = min(draft_tokens_per_round, max_tokens - len(all_tokens))
            active_n = self.num_candidates

            draft_start = time.time()

            # Check if we can skip draft generation due to optimistic hit
            skip_draft = False
            if optimistic_tokens and bet_hit:
                # Use optimistic tokens as draft candidates
                candidates = [{
                    'draft_token_ids': optimistic_tokens[:num_to_draft],
                    'draft_logprobs': [0.0] * min(len(optimistic_tokens), num_to_draft),
                }]
                # For multi-candidate, we only have 1 optimistic candidate
                active_n = 1
                skip_draft = True
                draft_time = 0.0
                print(f"  Round {speculation_rounds}: Using {len(candidates[0]['draft_token_ids'])} optimistic tokens as draft")
                # Extend current_token_ids with the optimistic tokens to update prefix
                # (They'll be verified in the next round)
                optimistic_tokens = []

            if not skip_draft:
                # Reset optimistic state
                optimistic_tokens = []
                bet_hit = False

                if active_n > 1:
                    sampling_params = SamplingParams(
                        temperature=self.candidate_temperature,
                        top_p=self.candidate_top_p,
                        top_k=request.params.top_k if request.params.top_k > 0 else -1,
                        max_tokens=num_to_draft,
                        logprobs=5,
                        n=active_n,
                    )
                else:
                    sampling_params = SamplingParams(
                        temperature=request.params.temperature if request.params.temperature > 0 else 0.8,
                        top_k=request.params.top_k if request.params.top_k > 0 else -1,
                        top_p=0.95,
                        max_tokens=num_to_draft,
                        logprobs=5,
                        seed=42,
                    )

                try:
                    outputs = self.llm.generate(
                        prompts=[{"prompt_token_ids": current_token_ids}],
                        sampling_params=sampling_params,
                        use_tqdm=False,
                    )
                    draft_outputs = outputs[0].outputs
                except Exception:
                    if active_n > 1:
                        draft_outputs = []
                        for seed_i in range(active_n):
                            sp = SamplingParams(
                                temperature=self.candidate_temperature,
                                top_p=self.candidate_top_p,
                                top_k=request.params.top_k if request.params.top_k > 0 else -1,
                                max_tokens=num_to_draft,
                                logprobs=5,
                                seed=seed_i + speculation_rounds * 100,
                            )
                            out = self.llm.generate(prompts=[{"prompt_token_ids": current_token_ids}], sampling_params=sp, use_tqdm=False)
                            draft_outputs.append(out[0].outputs[0])
                    else:
                        raise

                draft_time = (time.time() - draft_start) * 1000

                # Build candidates list
                candidates = []
                for draft_output in draft_outputs:
                    d_token_ids = list(draft_output.token_ids)
                    d_logprobs = []
                    if draft_output.logprobs:
                        for token_logprobs in draft_output.logprobs:
                            token_id = list(token_logprobs.keys())[0]
                            d_logprobs.append(token_logprobs[token_id].logprob)
                    candidates.append({
                        'draft_token_ids': d_token_ids,
                        'draft_logprobs': d_logprobs,
                    })

            if not candidates or not candidates[0]['draft_token_ids']:
                break

            if not skip_draft:
                print(f"  Round {speculation_rounds}: Drafted {len(candidates)} candidate(s) "
                      f"(len={[len(c['draft_token_ids']) for c in candidates]}) in {draft_time:.1f}ms")
                for ci, c in enumerate(candidates):
                    draft_text = self.tokenizer.decode(c['draft_token_ids'], skip_special_tokens=True)
                    print(f"    Candidate {ci}: {draft_text!r}")

            timing_draft_ms.append(draft_time)

            # ── Step C: Fire verification + optimistic poll loop ──
            try:
                handle = self._spawn_verification(request, current_token_ids, candidates, active_n)
                pending_spawn_time = time.time()
                pending_verify = _VerifyResult(handle)
                pending_candidates = candidates
                pending_active_n = active_n

                # Optimistic generation
                opt_start = time.time()
                tokens_remaining = max_tokens - len(all_tokens) - num_to_draft
                if self.optimistic_prefill and tokens_remaining > 0:
                    bet_idx = self._pick_best_candidate(candidates)
                    pending_bet_idx = bet_idx

                    # Build optimistic prefix: current tokens + bet candidate's draft tokens
                    bet_candidate = candidates[bet_idx]
                    optimistic_prefix_ids = list(current_token_ids) + list(bet_candidate['draft_token_ids'])

                    optimistic_tokens = []
                    num_opt_to_gen = min(draft_tokens_per_round, tokens_remaining)

                    # Single batched generate call instead of per-token loop
                    opt_params = SamplingParams(
                        temperature=request.params.temperature if request.params.temperature > 0 else 0.8,
                        top_k=request.params.top_k if request.params.top_k > 0 else -1,
                        top_p=0.95,
                        max_tokens=num_opt_to_gen,
                        logprobs=5,
                        seed=42,
                    )
                    try:
                        opt_out = self.llm.generate(
                            prompts=[{"prompt_token_ids": optimistic_prefix_ids}],
                            sampling_params=opt_params,
                            use_tqdm=False,
                        )
                        raw_opt_tokens = list(opt_out[0].outputs[0].token_ids)
                        # Filter out EOS tokens and truncate at first EOS
                        for j, tid in enumerate(raw_opt_tokens):
                            if eos_token_ids and tid in eos_token_ids:
                                break
                            optimistic_tokens.append(tid)
                    except Exception:
                        pass

                    if optimistic_tokens:
                        print(f"    Optimistic: generated {len(optimistic_tokens)} tokens while waiting")
                else:
                    pending_bet_idx = None

                opt_time = (time.time() - opt_start) * 1000
                timing_optimistic_ms.append(opt_time)

                round_total = draft_time + opt_time
                print(f"  Round {speculation_rounds} timing: draft={draft_time:.1f}ms  optimistic={opt_time:.1f}ms")

            except Exception as e:
                # Fallback to blocking .remote() if .spawn() fails
                print(f"  .spawn() failed ({e}), falling back to blocking .remote()")
                pending_verify = None
                pending_bet_idx = None
                optimistic_tokens = []

                verify_start = time.time()
                try:
                    if active_n > 1:
                        verify_response = self.verification_service.verify_multi_candidate.remote(
                            request_id=request.request_id,
                            session_id="session-0",
                            prefix_token_ids=list(current_token_ids),
                            candidates=candidates,
                            temperature=request.params.temperature if request.params.temperature > 0 else 0.8,
                            top_k=request.params.top_k if request.params.top_k > 0 else -1,
                        )

                        best_idx = verify_response["best_candidate_idx"]
                        best_result = verify_response["candidate_results"][best_idx]
                        num_accepted = best_result["num_accepted"]
                        best_draft = candidates[best_idx]['draft_token_ids']

                        accepted_lengths = [r["num_accepted"] for r in verify_response["candidate_results"]]
                        self.per_round_acceptance_lengths.append(accepted_lengths)
                        print(f"    Accepted lengths: {accepted_lengths}, best_idx={best_idx}")

                        if best_idx < len(self.candidate_win_counts):
                            self.candidate_win_counts[best_idx] += 1

                        total_draft_generated += len(best_draft)
                        total_draft_accepted += num_accepted

                        verify_result = {
                            "num_accepted_tokens": num_accepted,
                            "acceptance_mask": best_result["acceptance_mask"],
                            "corrected_token_ids": best_result["corrected_token_ids"],
                            "corrected_logprobs": best_result["corrected_logprobs"],
                            "next_token_id": best_result["next_token_id"],
                            "next_token_logprob": best_result["next_token_logprob"],
                        }
                    else:
                        draft_token_ids = candidates[0]['draft_token_ids']
                        draft_logprobs = candidates[0]['draft_logprobs']
                        total_draft_generated += len(draft_token_ids)

                        verify_result = self.verification_service.verify_draft.remote(
                            request_id=request.request_id,
                            session_id="session-0",
                            prefix_token_ids=list(current_token_ids),
                            draft_token_ids=list(draft_token_ids),
                            draft_logprobs=list(draft_logprobs),
                            temperature=request.params.temperature if request.params.temperature > 0 else 0.8,
                            top_k=request.params.top_k if request.params.top_k > 0 else -1,
                        )

                        num_accepted = verify_result["num_accepted_tokens"]
                        total_draft_accepted += num_accepted
                        best_draft = draft_token_ids

                    if active_n > 1:
                        timing_verify_ms.append(verify_response.get("verification_time_ms", 0.0))
                    else:
                        timing_verify_ms.append(verify_result.get("verification_time_ms", 0.0))

                    process_start = time.time()

                    acceptance_rate_round = num_accepted / len(best_draft) if best_draft else 0.0
                    print(f"    Verified: {num_accepted}/{len(best_draft)} accepted ({acceptance_rate_round:.1%})")

                    # Build round_token_events for streaming
                    round_token_events = []
                    accepted_tokens = best_draft[:num_accepted]
                    current_token_ids.extend(accepted_tokens)
                    for token_id in accepted_tokens:
                        round_token_events.append({"text": self.tokenizer.decode([token_id]), "type": "accepted", "token_id": token_id, "logprob": 0.0})
                    if num_accepted < len(best_draft):
                        rejected_id = best_draft[num_accepted]
                        round_token_events.append({"text": self.tokenizer.decode([rejected_id]), "type": "rejected", "token_id": rejected_id, "logprob": 0.0})
                    for i, token_id in enumerate(verify_result["corrected_token_ids"]):
                        corrected_logprobs = verify_result["corrected_logprobs"]
                        round_token_events.append({"text": self.tokenizer.decode([token_id]), "type": "corrected", "token_id": token_id, "logprob": corrected_logprobs[i] if i < len(corrected_logprobs) else 0.0})

                    if verify_result["corrected_token_ids"]:
                        current_token_ids.extend(verify_result["corrected_token_ids"])
                        print(f"    Corrected: +{len(verify_result['corrected_token_ids'])} tokens from target")

                    eos_reached = False
                    for token_id in accepted_tokens:
                        token = Token(
                            token_id=token_id,
                            text=self.tokenizer.decode([token_id]),
                            logprob=0.0,
                        )
                        all_tokens.append(token)
                        if eos_token_ids and token_id in eos_token_ids:
                            eos_reached = True
                            break

                    if not eos_reached:
                        for i, token_id in enumerate(verify_result["corrected_token_ids"]):
                            corrected_logprobs = verify_result["corrected_logprobs"]
                            token = Token(
                                token_id=token_id,
                                text=self.tokenizer.decode([token_id]),
                                logprob=corrected_logprobs[i] if i < len(corrected_logprobs) else 0.0,
                            )
                            all_tokens.append(token)
                            if eos_token_ids and token_id in eos_token_ids:
                                eos_reached = True
                                break

                    if not eos_reached and eos_token_ids and verify_result["next_token_id"] in eos_token_ids:
                        token = Token(
                            token_id=verify_result["next_token_id"],
                            text=self.tokenizer.decode([verify_result["next_token_id"]]),
                            logprob=verify_result["next_token_logprob"] or 0.0,
                        )
                        all_tokens.append(token)
                        current_token_ids.append(verify_result["next_token_id"])
                        eos_reached = True

                    # Check for repetition loop
                    if not eos_reached and len(all_tokens) >= REPEAT_WINDOW:
                        last_ids = [t.token_id for t in all_tokens[-REPEAT_WINDOW:]]
                        if len(set(last_ids)) == 1:
                            print(f"    Repetition detected (token {last_ids[0]} repeated {REPEAT_WINDOW}x), ending generation")
                            eos_reached = True
                        round_token_events.append({"text": token.text, "type": "accepted", "token_id": token.token_id, "logprob": token.logprob})

                    # Yield round event for fallback path
                    round_event = {
                        "round_num": speculation_rounds,
                        "drafted": len(best_draft),
                        "accepted": num_accepted,
                        "corrected": len(verify_result["corrected_token_ids"]),
                        "verification_time_ms": float(verify_result.get("verification_time_ms", 0.0)),
                        "acceptance_rate": float(verify_result.get("acceptance_rate", acceptance_rate_round)),
                    }
                    yield ("round", round_event, round_token_events)

                    if eos_reached:
                        if eos_token_ids:
                            eos_idx = next((i for i, tid in enumerate(current_token_ids) if tid in eos_token_ids), None)
                            if eos_idx is not None:
                                current_token_ids = current_token_ids[:eos_idx + 1]
                        print(f"    EOS token reached, ending generation")
                        process_time = (time.time() - process_start) * 1000
                        timing_process_ms.append(process_time)
                        break

                    process_time = (time.time() - process_start) * 1000
                    timing_process_ms.append(process_time)

                    round_total = draft_time + verify_time + process_time
                    idle_pct = (verify_time / round_total * 100) if round_total > 0 else 0.0
                    print(f"  Round {speculation_rounds} timing (fallback): draft={draft_time:.1f}ms  verify={verify_time:.1f}ms  process={process_time:.1f}ms  (idle={idle_pct:.1f}%)")
                except Exception as e2:
                    print(f"Error during verification: {e2}")
                    import traceback
                    traceback.print_exc()
                    break

        # Generate final response
        elapsed = (time.time() - start_time) * 1000
        final_text = self.tokenizer.decode(current_token_ids, skip_special_tokens=True)
        acceptance_rate = total_draft_accepted / total_draft_generated if total_draft_generated > 0 else 0.0

        print(f"\n{'='*80}")
        print(f"Inference complete!")
        print(f"   Total tokens: {len(all_tokens)}")
        print(f"   Draft generated: {total_draft_generated}")
        print(f"   Draft accepted: {total_draft_accepted} ({acceptance_rate:.1%})")
        print(f"   Speculation rounds: {speculation_rounds}")
        if self.num_candidates > 1:
            print(f"   Num candidates: {self.num_candidates}")
            print(f"   Candidate wins: {self.candidate_win_counts}")
        if self.optimistic_prefill:
            total_opt = self._optimistic_hits + self._optimistic_misses
            hit_rate = (self._optimistic_hits / total_opt * 100) if total_opt > 0 else 0.0
            print(f"   Optimistic prefill: {self._optimistic_hits} hits / {self._optimistic_misses} misses ({hit_rate:.1f}% hit rate)")
        print(f"   Total time: {elapsed:.1f}ms ({len(all_tokens) / (elapsed/1000):.1f} tokens/sec)")
        print(f"   Result: {final_text!r}")

        # Timing breakdown
        total_draft_time = sum(timing_draft_ms)
        total_verify_time = sum(timing_verify_ms)
        total_process_time = sum(timing_process_ms)
        total_optimistic_time = sum(timing_optimistic_ms)
        num_rounds = len(timing_draft_ms)
        total_tracked = total_draft_time + total_verify_time + total_process_time + total_optimistic_time
        idle_pct = (total_verify_time / total_tracked * 100) if total_tracked > 0 else 0.0

        print(f"\nTiming breakdown:")
        print(f"   Total draft generation: {total_draft_time:.1f}ms (avg {total_draft_time/num_rounds:.1f}ms/round)" if num_rounds else "   Total draft generation: 0.0ms")
        print(f"   Total verification (GPU): {total_verify_time:.1f}ms (avg {total_verify_time/num_rounds:.1f}ms/round)" if num_rounds else "   Total verification (GPU): 0.0ms")
        print(f"   Total processing: {total_process_time:.1f}ms (avg {total_process_time/num_rounds:.1f}ms/round)" if num_rounds else "   Total processing: 0.0ms")
        print(f"   Total optimistic gen: {total_optimistic_time:.1f}ms (avg {total_optimistic_time/num_rounds:.1f}ms/round)" if num_rounds else "   Total optimistic gen: 0.0ms")
        print(f"   Draft GPU idle: {idle_pct:.1f}% of wall time")
        print(f"{'='*80}\n")

        # Store timing data for benchmark access
        self._last_timing = {
            'timing_draft_ms': timing_draft_ms,
            'timing_verify_ms': timing_verify_ms,
            'timing_process_ms': timing_process_ms,
            'timing_optimistic_ms': timing_optimistic_ms,
        }

        response = speculative_decoding_pb2.InferenceJobResponse(
            request_id=request.request_id,
            generated_text=final_text,
            tokens=[common_pb2.Token(token_id=t.token_id, text=t.text, logprob=t.logprob) for t in all_tokens],
            status=common_pb2.STATUS_SUCCESS,
            total_tokens=len(all_tokens),
            draft_tokens_generated=total_draft_generated,
            draft_tokens_accepted=total_draft_accepted,
            generation_time_ms=elapsed,
            acceptance_rate=acceptance_rate,
            speculation_rounds=speculation_rounds,
        )

        yield ("done", response, [])

    def execute_inference(self, request):
        """Execute inference and return only final response (non-streaming helper)."""
        result = None
        for event_type, data, _ in self.execute_inference_stream(request):
            if event_type == "done":
                result = data
        return result

    def __del__(self):
        """Cleanup"""
        if hasattr(self, 'llm'):
            try:
                del self.llm.llm_engine
                del self.llm
            except:
                pass


def main():
    """Example usage"""
    print("\n" + "="*80)
    print("Draft Node Client - Speculative Decoding Demo")
    print("="*80 + "\n")

    client = DraftNodeClient()

    test_prompts = [
        "Hello, my name is",
        "The president of the United States is",
        "The capital of France is",
        "The future of AI is",
    ]

    for prompt in test_prompts:
        request = speculative_decoding_pb2.InferenceJobRequest(
            request_id=f"req-{hash(prompt) % 10000}",
            prompt=prompt,
            params=common_pb2.InferenceParams(
                max_tokens=16,
                temperature=0.8,
                top_k=50,
                draft_tokens=5,
            ),
            model_id="Qwen/Qwen2.5-0.5B-Instruct",
            timestamp=int(time.time() * 1000),
        )

        response = client.execute_inference(request)

        print(f"\nFinal Stats:")
        print(f"   Status: {common_pb2.StatusCode.Name(response.status)}")
        print(f"   Acceptance Rate: {response.acceptance_rate:.1%}")
        print(f"   Speed: {response.total_tokens / (response.generation_time_ms/1000):.1f} tokens/sec")
        print("\n" + "-"*80 + "\n")

        time.sleep(1)


if __name__ == '__main__':
    main()
