"""
Draft Node - DraftNodeService Implementation
Generates draft tokens and coordinates with verification service.
"""
import grpc
import sys
import os
from vllm import LLM, SamplingParams
import time

# Add proto directory to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'proto'))

# Import generated protobuf code
import common_pb2
import speculative_decoding_pb2
import speculative_decoding_pb2_grpc


class DraftNodeClient:
    def __init__(
        self,
        draft_model="Qwen/Qwen2.5-1.5B-Instruct",  # Match Qwen family for target
        verification_server="100.82.221.67:50",
        num_draft_tokens=5,
    ):
        print(f"Initializing draft node with model: {draft_model}")
        self.llm = LLM(
            model=draft_model,
            gpu_memory_utilization=0.3,  # Adjusted for Llama
            max_model_len=4096,  # Match target context length
        )

        self.num_draft_tokens = num_draft_tokens

        # Load tokenizer
        from transformers import AutoTokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(draft_model)

        # Connect to verification service
        print(f"Connecting to verification service at {verification_server}")
        self.channel = grpc.insecure_channel(verification_server)
        self.verification_stub = speculative_decoding_pb2_grpc.VerificationServiceStub(self.channel)

        print("Draft node ready!")

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
        print(f"🚀 Starting inference for request: {request.request_id}")
        print(f"   Prompt: {request.prompt!r}")
        print(f"   Max tokens: {max_tokens}")
        print(f"   Draft tokens/round: {draft_tokens_per_round}")
        print(f"{'='*80}\n")

        while len(all_tokens) < max_tokens:
            speculation_rounds += 1

            # Step 1: Generate draft tokens
            num_to_draft = min(draft_tokens_per_round, max_tokens - len(all_tokens))

            sampling_params = SamplingParams(
                temperature=request.params.temperature if request.params.temperature > 0 else 0.8,
                top_k=request.params.top_k if request.params.top_k > 0 else -1,
                top_p=0.95,
                max_tokens=num_to_draft,
                logprobs=5,  # Get more logprobs
                seed=42,  # Same seed as target for testing
            )

            draft_start = time.time()
            outputs = self.llm.generate(
                prompts=[current_text],
                sampling_params=sampling_params,
                use_tqdm=False,
            )

            draft_output = outputs[0].outputs[0]
            draft_token_ids = draft_output.token_ids
            draft_time = (time.time() - draft_start) * 1000

            if not draft_token_ids:
                break

            total_draft_generated += len(draft_token_ids)

            # Extract draft logprobs
            draft_logprobs = []
            if draft_output.logprobs:
                for token_logprobs in draft_output.logprobs:
                    token_id = list(token_logprobs.keys())[0]
                    draft_logprobs.append(token_logprobs[token_id].logprob)

            draft_text = self.tokenizer.decode(draft_token_ids, skip_special_tokens=True)
            print(f"  Round {speculation_rounds}: Drafted {len(draft_token_ids)} tokens in {draft_time:.1f}ms")
            print(f"    Draft: {draft_text!r}")

            # Step 2: Send to verification service
            try:
                verify_request = speculative_decoding_pb2.VerificationRequest(
                    request_id=request.request_id,
                    session_id="session-0",  # Could implement session management
                    prefix_token_ids=current_token_ids,
                    draft_token_ids=draft_token_ids,
                    draft_logprobs=draft_logprobs,
                    temperature=request.params.temperature if request.params.temperature > 0 else 0.8,
                    top_k=request.params.top_k if request.params.top_k > 0 else -1,
                )

                verify_response = self.verification_stub.VerifyDraft(verify_request)

                num_accepted = verify_response.num_accepted_tokens
                total_draft_accepted += num_accepted

                print(f"    Verified: {num_accepted}/{len(draft_token_ids)} accepted ({verify_response.acceptance_rate:.1%})")

                # Accept the verified tokens
                accepted_tokens = draft_token_ids[:num_accepted]
                current_token_ids.extend(accepted_tokens)

                # Add corrected token if any
                if verify_response.corrected_token_ids:
                    current_token_ids.extend(verify_response.corrected_token_ids)
                    print(f"    Corrected: +{len(verify_response.corrected_token_ids)} tokens from target")

                # Add to result
                eos_reached = False
                for token_id in accepted_tokens:
                    token = common_pb2.Token(
                        token_id=token_id,
                        text=self.tokenizer.decode([token_id]),
                        logprob=0.0,  # Could track this
                    )
                    all_tokens.append(token)
                    if eos_token_ids and token_id in eos_token_ids:
                        eos_reached = True
                        break

                if not eos_reached:
                    for i, token_id in enumerate(verify_response.corrected_token_ids):
                        token = common_pb2.Token(
                            token_id=token_id,
                            text=self.tokenizer.decode([token_id]),
                            logprob=verify_response.corrected_logprobs[i] if i < len(verify_response.corrected_logprobs) else 0.0,
                        )
                        all_tokens.append(token)
                        if eos_token_ids and token_id in eos_token_ids:
                            eos_reached = True
                            break

                # Check next_token_id from target (when all draft tokens accepted)
                if not eos_reached and eos_token_ids and verify_response.next_token_id in eos_token_ids:
                    token = common_pb2.Token(
                        token_id=verify_response.next_token_id,
                        text=self.tokenizer.decode([verify_response.next_token_id]),
                        logprob=verify_response.next_token_logprob if verify_response.next_token_logprob else 0.0,
                    )
                    all_tokens.append(token)
                    current_token_ids.append(verify_response.next_token_id)
                    eos_reached = True

                if eos_reached:
                    # Truncate current_token_ids to remove any tokens after EOS
                    eos_idx = next((i for i, tid in enumerate(current_token_ids) if tid in eos_token_ids), None)
                    if eos_idx is not None:
                        current_token_ids = current_token_ids[:eos_idx + 1]
                    print(f"    EOS token reached, ending generation")
                    break

                # Update current text
                current_text = self.tokenizer.decode(current_token_ids, skip_special_tokens=True)

            except grpc.RpcError as e:
                print(f"❌ gRPC error: {e}")
                break
            except Exception as e:
                print(f"❌ Error during verification: {e}")
                import traceback
                traceback.print_exc()
                break

        # Generate final response
        elapsed = (time.time() - start_time) * 1000
        final_text = self.tokenizer.decode(current_token_ids, skip_special_tokens=True)
        acceptance_rate = total_draft_accepted / total_draft_generated if total_draft_generated > 0 else 0.0

        print(f"\n{'='*80}")
        print(f"✅ Inference complete!")
        print(f"   Total tokens: {len(all_tokens)}")
        print(f"   Draft generated: {total_draft_generated}")
        print(f"   Draft accepted: {total_draft_accepted} ({acceptance_rate:.1%})")
        print(f"   Speculation rounds: {speculation_rounds}")
        print(f"   Total time: {elapsed:.1f}ms ({len(all_tokens) / (elapsed/1000):.1f} tokens/sec)")
        print(f"   Result: {final_text!r}")
        print(f"{'='*80}\n")

        response = speculative_decoding_pb2.InferenceJobResponse(
            request_id=request.request_id,
            generated_text=final_text,
            tokens=all_tokens,
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
        if hasattr(self, 'channel'):
            self.channel.close()
        if hasattr(self, 'llm'):
            try:
                del self.llm.llm_engine
                del self.llm
            except:
                pass


def main():
    """Example usage"""
    print("\n" + "="*80)
    print("📝 Draft Node Client - Speculative Decoding Demo")
    print("="*80 + "\n")

    client = DraftNodeClient()

    # Create test requests
    test_prompts = [
        "Hello, my name is",
        "The president of the United States is",
        "The capital of France is",
        "The future of AI is",
    ]

    for prompt in test_prompts:
        # Create inference request
        request = speculative_decoding_pb2.InferenceJobRequest(
            request_id=f"req-{hash(prompt) % 10000}",
            prompt=prompt,
            params=common_pb2.InferenceParams(
                max_tokens=16,
                temperature=0.8,
                top_k=50,
                draft_tokens=5,
            ),
            model_id="meta-llama/Llama-3.2-3B",
            timestamp=int(time.time() * 1000),
        )

        # Execute inference
        response = client.execute_inference(request)

        print(f"\n📊 Final Stats:")
        print(f"   Status: {common_pb2.StatusCode.Name(response.status)}")
        print(f"   Acceptance Rate: {response.acceptance_rate:.1%}")
        print(f"   Speed: {response.total_tokens / (response.generation_time_ms/1000):.1f} tokens/sec")
        print("\n" + "-"*80 + "\n")

        time.sleep(1)  # Small delay between requests


if __name__ == '__main__':
    main()
