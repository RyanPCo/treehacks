"""
Draft Node - DraftNodeService Implementation
Generates draft tokens and coordinates with Modal verification service.
"""
import modal
import sys
import os
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


class DraftNodeClient:
    def __init__(
        self,
        draft_model="Qwen/Qwen3-1.7B-Instruct",
        num_draft_tokens=5,
        num_candidates=1,
        candidate_temperature=1.0,
        candidate_top_p=0.9,
    ):
        print(f"Initializing draft node with model: {draft_model}")
        self.llm = LLM(
            model=draft_model,
            gpu_memory_utilization=0.3,
            max_model_len=4096,
        )

        self.num_draft_tokens = num_draft_tokens
        self.num_candidates = num_candidates
        self.candidate_temperature = candidate_temperature
        self.candidate_top_p = candidate_top_p

        # Adaptive N state
        self._adaptive_window = []
        self._adaptive_window_size = 5
        self._current_n = num_candidates

        # Multi-candidate statistics
        self.candidate_win_counts = [0] * num_candidates
        self.per_round_acceptance_lengths = []

        from transformers import AutoTokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(draft_model)

        # Connect to Modal verification service
        print("Connecting to Modal verification service...")
        self.verification_service = modal.Cls.from_name(
            "treehacks-verification-service", "VerificationService"
        )()

        print(f"Draft node ready! (num_candidates={num_candidates})")

    def execute_inference(self, request):
        """
        Execute inference with speculative decoding.

        Args:
            request: InferenceJobRequest

        Returns:
            InferenceJobResponse
        """
        start_time = time.time()

        current_text = request.prompt
        current_token_ids = self.tokenizer.encode(current_text)
        all_tokens = []

        # Statistics
        total_draft_generated = 0
        total_draft_accepted = 0
        speculation_rounds = 0

        max_tokens = request.params.max_tokens if request.params.max_tokens > 0 else 16
        draft_tokens_per_round = request.params.draft_tokens if request.params.draft_tokens > 0 else self.num_draft_tokens

        # Collect all EOS token IDs (Qwen has <|endoftext|> and <|im_end|>, etc.)
        eos_token_ids = set()
        if getattr(self.tokenizer, 'eos_token_id', None) is not None:
            eos_token_ids.add(self.tokenizer.eos_token_id)
        for token in ("<|endoftext|>", "<|im_end|>"):
            if token in self.tokenizer.get_vocab():
                eos_token_ids.add(self.tokenizer.convert_tokens_to_ids(token))

        print(f"\n{'='*80}")
        print(f"Starting inference for request: {request.request_id}")
        print(f"   Prompt: {request.prompt!r}")
        print(f"   Max tokens: {max_tokens}")
        print(f"   Draft tokens/round: {draft_tokens_per_round}")
        print(f"   Num candidates: {self._current_n}")
        print(f"{'='*80}\n")

        while len(all_tokens) < max_tokens:
            speculation_rounds += 1

            # Step 1: Generate draft tokens (possibly multiple candidates)
            num_to_draft = min(draft_tokens_per_round, max_tokens - len(all_tokens))
            active_n = self._current_n

            draft_start = time.time()

            if active_n > 1:
                # Multi-candidate: use temperature sampling with n completions
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
                    prompts=[current_text],
                    sampling_params=sampling_params,
                    use_tqdm=False,
                )
                draft_outputs = outputs[0].outputs
            except Exception:
                # Fallback: n>1 not supported (e.g. Metal backend), generate separately
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
                        out = self.llm.generate(prompts=[current_text], sampling_params=sp, use_tqdm=False)
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

            # Track draft tokens (count from best candidate after verification)
            print(f"  Round {speculation_rounds}: Drafted {len(candidates)} candidate(s) "
                  f"(len={[len(c['draft_token_ids']) for c in candidates]}) in {draft_time:.1f}ms")
            for ci, c in enumerate(candidates):
                draft_text = self.tokenizer.decode(c['draft_token_ids'], skip_special_tokens=True)
                print(f"    Candidate {ci}: {draft_text!r}")

            # Step 2: Send to verification service
            try:
                if active_n > 1:
                    # Multi-candidate verification
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

                    # Log all candidates
                    accepted_lengths = [r["num_accepted"] for r in verify_response["candidate_results"]]
                    self.per_round_acceptance_lengths.append(accepted_lengths)
                    print(f"    Accepted lengths: {accepted_lengths}, best_idx={best_idx}")

                    # Track win counts
                    if best_idx < len(self.candidate_win_counts):
                        self.candidate_win_counts[best_idx] += 1

                    total_draft_generated += len(best_draft)
                    total_draft_accepted += num_accepted

                    # Use best candidate's result
                    verify_result = {
                        "num_accepted_tokens": num_accepted,
                        "acceptance_mask": best_result["acceptance_mask"],
                        "corrected_token_ids": best_result["corrected_token_ids"],
                        "corrected_logprobs": best_result["corrected_logprobs"],
                        "next_token_id": best_result["next_token_id"],
                        "next_token_logprob": best_result["next_token_logprob"],
                    }

                    # Adaptive N: reduce if acceptance consistently low
                    best_rate = num_accepted / len(best_draft) if best_draft else 0.0
                    self._adaptive_window.append(best_rate)
                    if len(self._adaptive_window) >= self._adaptive_window_size:
                        avg_rate = sum(self._adaptive_window[-self._adaptive_window_size:]) / self._adaptive_window_size
                        if avg_rate < 0.2 and self._current_n > 1:
                            self._current_n -= 1
                            self._adaptive_window.clear()
                            print(f"    [Adaptive] Reducing N to {self._current_n} (avg acceptance {avg_rate:.1%})")

                else:
                    # Single candidate (original path)
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

                acceptance_rate_round = num_accepted / len(best_draft) if best_draft else 0.0
                print(f"    Verified: {num_accepted}/{len(best_draft)} accepted ({acceptance_rate_round:.1%})")

                # Accept the verified tokens
                accepted_tokens = best_draft[:num_accepted]
                current_token_ids.extend(accepted_tokens)

                # Add corrected token if any
                if verify_result["corrected_token_ids"]:
                    current_token_ids.extend(verify_result["corrected_token_ids"])
                    print(f"    Corrected: +{len(verify_result['corrected_token_ids'])} tokens from target")

                # Add to result
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

                if eos_reached:
                    eos_idx = next((i for i, tid in enumerate(current_token_ids) if tid in eos_token_ids), None)
                    if eos_idx is not None:
                        current_token_ids = current_token_ids[:eos_idx + 1]
                    print(f"    EOS token reached, ending generation")
                    break

                # Update current text
                current_text = self.tokenizer.decode(current_token_ids, skip_special_tokens=True)

            except Exception as e:
                print(f"Error during verification: {e}")
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
            print(f"   Num candidates: {self.num_candidates} (adaptive N: {self._current_n})")
            print(f"   Candidate wins: {self.candidate_win_counts}")
        print(f"   Total time: {elapsed:.1f}ms ({len(all_tokens) / (elapsed/1000):.1f} tokens/sec)")
        print(f"   Result: {final_text!r}")
        print(f"{'='*80}\n")

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

        return response

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
            model_id="Qwen/Qwen3-1.7B-Instruct",
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
