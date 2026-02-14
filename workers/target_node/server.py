"""
Target Node - VerificationService Implementation
Runs the powerful model to verify draft tokens from draft nodes.
"""
import grpc
from concurrent import futures
import sys
import os
from vllm import LLM, SamplingParams
import time
import torch

# Add proto directory to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'proto'))

# Import generated protobuf code
import common_pb2
import speculative_decoding_pb2
import speculative_decoding_pb2_grpc

# Import verification strategies
from verification_strategies import get_strategy


class VerificationServiceImpl(speculative_decoding_pb2_grpc.VerificationServiceServicer):
    def __init__(
        self,
        model_name="Qwen/Qwen2.5-0.5B-Instruct",
        strategy="deterministic",
        strategy_kwargs=None,
        gpu_memory_utilization=0.98,
        max_model_len=1024,
        max_num_seqs=2,
        enforce_eager=True,
    ):
        print(f"Initializing verification service with model: {model_name}")
        print(f"Using verification strategy: {strategy}")
        if torch.cuda.is_available():
            free_bytes, total_bytes = torch.cuda.mem_get_info(0)
            free_ratio = free_bytes / total_bytes
            # Keep a small safety margin to avoid startup failures from minor memory drift.
            safe_utilization = max(0.5, min(gpu_memory_utilization, free_ratio - 0.02))
            if safe_utilization < gpu_memory_utilization:
                print(
                    f"Adjusting gpu_memory_utilization from {gpu_memory_utilization:.2f} "
                    f"to {safe_utilization:.2f} based on current free VRAM."
                )
            gpu_memory_utilization = safe_utilization

        self.llm = LLM(
            model=model_name,
            gpu_memory_utilization=gpu_memory_utilization,
            max_model_len=max_model_len,
            max_num_seqs=max_num_seqs,
            enforce_eager=enforce_eager,
        )

        # Load tokenizer for decoding
        from transformers import AutoTokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)

        # Initialize verification strategy
        strategy_kwargs = strategy_kwargs or {}
        self.verification_strategy = get_strategy(strategy, **strategy_kwargs)

        print(f"Verification service ready with {strategy} strategy!")

    def VerifyDraft(self, request, context):
        """
        Verify draft tokens with the powerful model using probabilistic acceptance.

        Implements the speculative decoding algorithm from SLED paper:
        A draft token x̃ is accepted with probability:
            α = min(1, p_target(x̃) / p_draft(x̃))

        This ensures the output distribution matches the target model exactly.
        """
        start_time = time.time()

        try:
            # Decode the prefix to get the current prompt
            prefix_text = self.tokenizer.decode(request.prefix_token_ids, skip_special_tokens=True)

            # Number of draft tokens to verify
            num_draft_tokens = len(request.draft_token_ids)

            if num_draft_tokens == 0:
                return speculative_decoding_pb2.VerificationResponse(
                    request_id=request.request_id,
                    session_id=request.session_id,
                    num_accepted_tokens=0,
                    acceptance_mask=[],
                    corrected_token_ids=[],
                    corrected_logprobs=[],
                    next_token_id=0,
                    next_token_logprob=0.0,
                    verification_time_ms=0.0,
                    acceptance_rate=0.0,
                )

            # Generate tokens with the target model
            # Use SAME parameters as draft to maximize agreement
            sampling_params = SamplingParams(
                temperature=request.temperature if request.temperature > 0 else 0.8,
                top_k=request.top_k if request.top_k > 0 else -1,
                top_p=0.95,  # Match draft default
                max_tokens=num_draft_tokens + 1,  # Generate one extra for next token
                logprobs=5,  # Get more logprobs for better probability estimates
                seed=42,  # Fixed seed for reproducibility during testing
            )

            print(f"  Verifying {num_draft_tokens} draft tokens (temp={sampling_params.temperature}, top_k={sampling_params.top_k})")

            outputs = self.llm.generate(
                prompts=[prefix_text],
                sampling_params=sampling_params,
                use_tqdm=False,
            )

            target_output = outputs[0].outputs[0]
            target_tokens = target_output.token_ids

            # Use the configured verification strategy
            num_accepted, acceptance_mask, corrected_tokens, corrected_logprobs = \
                self.verification_strategy.verify(
                    draft_token_ids=list(request.draft_token_ids),
                    draft_logprobs=list(request.draft_logprobs),
                    target_token_ids=target_tokens,
                    target_logprobs=target_output.logprobs,
                )

            # Get next token after verification
            next_token_id = 0
            next_token_logprob = 0.0
            if len(target_tokens) > num_accepted:
                next_token_id = target_tokens[num_accepted]
                if target_output.logprobs and num_accepted < len(target_output.logprobs):
                    token_logprobs = target_output.logprobs[num_accepted]
                    if next_token_id in token_logprobs:
                        next_token_logprob = token_logprobs[next_token_id].logprob

            # Calculate acceptance rate
            acceptance_rate = num_accepted / num_draft_tokens if num_draft_tokens > 0 else 0.0

            # Calculate verification time
            verification_time = (time.time() - start_time) * 1000  # ms

            response = speculative_decoding_pb2.VerificationResponse(
                request_id=request.request_id,
                session_id=request.session_id,
                num_accepted_tokens=num_accepted,
                acceptance_mask=acceptance_mask,
                corrected_token_ids=corrected_tokens,
                corrected_logprobs=corrected_logprobs,
                next_token_id=next_token_id,
                next_token_logprob=next_token_logprob,
                verification_time_ms=verification_time,
                acceptance_rate=acceptance_rate,
            )

            print(f"✓ Verified {num_accepted}/{num_draft_tokens} tokens ({acceptance_rate:.1%}) in {verification_time:.1f}ms")

            return response

        except Exception as e:
            print(f"Error in VerifyDraft: {e}")
            import traceback
            traceback.print_exc()
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return speculative_decoding_pb2.VerificationResponse()

    def BatchVerify(self, request, context):
        """Batch verification for multiple sequences"""
        start_time = time.time()

        responses = []
        for req in request.requests:
            response = self.VerifyDraft(req, context)
            responses.append(response)

        total_time = (time.time() - start_time) * 1000

        return speculative_decoding_pb2.BatchVerificationResponse(
            responses=responses,
            total_batch_time_ms=total_time,
        )

    def __del__(self):
        """Cleanup on shutdown"""
        if hasattr(self, 'llm'):
            try:
                del self.llm.llm_engine
                del self.llm
            except:
                pass


def serve(
    port=50051,
    strategy="deterministic",
    strategy_kwargs=None,
    model_name="Qwen/Qwen2.5-0.5B-Instruct",
    gpu_memory_utilization=0.98,
    max_model_len=1024,
    max_num_seqs=2,
    enforce_eager=True,
):
    """Start the verification service gRPC server"""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    servicer = VerificationServiceImpl(
        model_name=model_name,
        strategy=strategy,
        strategy_kwargs=strategy_kwargs,
        gpu_memory_utilization=gpu_memory_utilization,
        max_model_len=max_model_len,
        max_num_seqs=max_num_seqs,
        enforce_eager=enforce_eager,
    )
    speculative_decoding_pb2_grpc.add_VerificationServiceServicer_to_server(servicer, server)

    server.add_insecure_port(f'[::]:{port}')
    server.start()

    print(f"\n{'='*80}")
    print(f"🎯 Verification Service (Target Node) started on port {port}")
    print(f"   Model: {model_name}")
    print(f"   Strategy: {strategy}")
    print(f"   gpu_memory_utilization: {gpu_memory_utilization}")
    print(f"   max_model_len: {max_model_len}")
    print(f"   max_num_seqs: {max_num_seqs}")
    print(f"   enforce_eager: {enforce_eager}")
    if strategy_kwargs:
        print(f"   Strategy params: {strategy_kwargs}")
    print(f"   Ready to verify draft tokens from draft nodes")
    print(f"{'='*80}\n")

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("\n\nShutting down verification service...")
        server.stop(0)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Target Node Verification Service')
    parser.add_argument('--port', type=int, default=50051, help='Port to listen on')
    parser.add_argument('--model', type=str, default='Qwen/Qwen3-32B-Instruct',
                        help='Target model to use (default: Qwen/Qwen2.5-3B-Instruct)')
    parser.add_argument('--strategy', type=str, default='probabilistic',
                        choices=['deterministic', 'probabilistic', 'threshold', 'greedy'],
                        help='Verification strategy to use')
    parser.add_argument('--threshold', type=float, default=0.1,
                        help='Threshold for threshold strategy (default: 0.1)')
    parser.add_argument('--verbose', action='store_true',
                        help='Enable verbose logging in verification')
    parser.add_argument('--gpu-memory-utilization', type=float, default=0.98,
                        help='Fraction of GPU memory budget for vLLM (default: 0.98)')
    parser.add_argument('--max-model-len', type=int, default=1024,
                        help='Maximum context length for KV cache sizing (default: 1024)')
    parser.add_argument('--max-num-seqs', type=int, default=2,
                        help='Maximum concurrent sequences (default: 2)')
    parser.add_argument('--no-enforce-eager', action='store_true',
                        help='Disable enforce_eager (may use more memory)')

    args = parser.parse_args()

    # Build strategy kwargs
    strategy_kwargs = {'verbose': args.verbose}
    if args.strategy == 'threshold':
        strategy_kwargs['threshold'] = args.threshold

    serve(
        port=args.port,
        strategy=args.strategy,
        strategy_kwargs=strategy_kwargs,
        model_name=args.model,
        gpu_memory_utilization=args.gpu_memory_utilization,
        max_model_len=args.max_model_len,
        max_num_seqs=args.max_num_seqs,
        enforce_eager=not args.no_enforce_eager,
    )
