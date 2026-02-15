"""
Target Node - VerificationService on Modal
Runs the powerful model on Modal GPUs to verify draft tokens from draft nodes.
"""
import modal
import sys
import os

app = modal.App("treehacks-verification-service")

# Image with all dependencies
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "vllm",
        "transformers",
        "numpy",
        "torch",
    )
    .add_local_dir(
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "proto"),
        remote_path="/app/proto",
    )
    .add_local_file(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "verification_strategies.py"),
        remote_path="/app/verification_strategies.py",
    )
)


@app.cls(
    image=image,
    gpu="H100",
    timeout=600,
    scaledown_window=300,
)
@modal.concurrent(max_inputs=10)
class VerificationService:
    model_name: str = "Qwen/Qwen3-32B-Instruct"
    strategy: str = "deterministic"

    @modal.enter()
    def setup(self):
        """Load model and tokenizer on container start."""
        from vllm import LLM
        from transformers import AutoTokenizer

        sys.path.insert(0, "/app/proto")
        sys.path.insert(0, "/app")

        print(f"Initializing verification service with model: {self.model_name}")
        print(f"Using verification strategy: {self.strategy}")

        self.llm = LLM(
            model=self.model_name,
            gpu_memory_utilization=0.90,
            max_model_len=4096,
            enable_prefix_caching=True,
        )
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)

        from verification_strategies import get_strategy
        self.verification_strategy = get_strategy(self.strategy)

        print("Verification service ready!")

    @modal.method()
    def verify_draft(
        self,
        request_id: str,
        session_id: str,
        prefix_token_ids: list[int],
        draft_token_ids: list[int],
        draft_logprobs: list[float],
        temperature: float = 0.8,
        top_k: int = -1,
    ) -> dict:
        """Verify draft tokens with the powerful model."""
        import time
        from vllm import SamplingParams

        start_time = time.time()

        num_draft_tokens = len(draft_token_ids)

        if num_draft_tokens == 0:
            return {
                "request_id": request_id,
                "session_id": session_id,
                "num_accepted_tokens": 0,
                "acceptance_mask": [],
                "corrected_token_ids": [],
                "corrected_logprobs": [],
                "next_token_id": 0,
                "next_token_logprob": 0.0,
                "verification_time_ms": 0.0,
                "acceptance_rate": 0.0,
            }

        sampling_params = SamplingParams(
            temperature=temperature if temperature > 0 else 0.8,
            top_k=top_k if top_k > 0 else -1,
            top_p=0.95,
            max_tokens=num_draft_tokens + 1,
            logprobs=5,
            seed=42,
        )

        print(f"  Verifying {num_draft_tokens} draft tokens (temp={sampling_params.temperature}, top_k={sampling_params.top_k})")

        outputs = self.llm.generate(
            prompts=[{"prompt_token_ids": prefix_token_ids}],
            sampling_params=sampling_params,
            use_tqdm=False,
        )

        target_output = outputs[0].outputs[0]
        target_tokens = target_output.token_ids

        num_accepted, acceptance_mask, corrected_tokens, corrected_logprobs = \
            self.verification_strategy.verify(
                draft_token_ids=draft_token_ids,
                draft_logprobs=draft_logprobs,
                target_token_ids=target_tokens,
                target_logprobs=target_output.logprobs,
            )

        next_token_id = 0
        next_token_logprob = 0.0
        if len(target_tokens) > num_accepted:
            next_token_id = target_tokens[num_accepted]
            if target_output.logprobs and num_accepted < len(target_output.logprobs):
                token_logprobs = target_output.logprobs[num_accepted]
                if next_token_id in token_logprobs:
                    next_token_logprob = token_logprobs[next_token_id].logprob

        acceptance_rate = num_accepted / num_draft_tokens if num_draft_tokens > 0 else 0.0
        verification_time = (time.time() - start_time) * 1000

        print(f"Verified {num_accepted}/{num_draft_tokens} tokens ({acceptance_rate:.1%}) in {verification_time:.1f}ms")

        return {
            "request_id": request_id,
            "session_id": session_id,
            "num_accepted_tokens": num_accepted,
            "acceptance_mask": acceptance_mask,
            "corrected_token_ids": corrected_tokens,
            "corrected_logprobs": corrected_logprobs,
            "next_token_id": next_token_id,
            "next_token_logprob": next_token_logprob,
            "verification_time_ms": verification_time,
            "acceptance_rate": acceptance_rate,
        }

    @modal.method()
    def verify_multi_candidate(
        self,
        request_id: str,
        session_id: str,
        prefix_token_ids: list[int],
        candidates: list[dict],
        temperature: float = 0.8,
        top_k: int = -1,
    ) -> dict:
        """Verify multiple draft candidates against a single target forward pass.

        Args:
            candidates: list of {draft_token_ids: list[int], draft_logprobs: list[float]}
        """
        import time
        from vllm import SamplingParams

        start_time = time.time()
        n = len(candidates)

        if n == 0:
            return {
                "request_id": request_id,
                "session_id": session_id,
                "candidate_results": [],
                "best_candidate_idx": -1,
                "verification_time_ms": 0.0,
            }

        # Determine max draft length across all candidates
        max_draft_len = max(len(c['draft_token_ids']) for c in candidates)

        if max_draft_len == 0:
            return {
                "request_id": request_id,
                "session_id": session_id,
                "candidate_results": [
                    {"num_accepted": 0, "acceptance_mask": [], "corrected_token_ids": [],
                     "corrected_logprobs": [], "next_token_id": 0, "next_token_logprob": 0.0,
                     "target_logprob_sum": 0.0}
                    for _ in range(n)
                ],
                "best_candidate_idx": 0,
                "verification_time_ms": 0.0,
            }

        # Single target model forward pass
        sampling_params = SamplingParams(
            temperature=temperature if temperature > 0 else 0.8,
            top_k=top_k if top_k > 0 else -1,
            top_p=0.95,
            max_tokens=max_draft_len + 1,
            logprobs=5,
            seed=42,
        )

        print(f"  Multi-candidate verify: {n} candidates, max_draft_len={max_draft_len}")

        outputs = self.llm.generate(
            prompts=[{"prompt_token_ids": prefix_token_ids}],
            sampling_params=sampling_params,
            use_tqdm=False,
        )

        target_output = outputs[0].outputs[0]
        target_tokens = list(target_output.token_ids)
        target_lps = target_output.logprobs

        # Vectorized batch verification
        batch_results = self.verification_strategy.verify_batch(
            candidates=candidates,
            target_token_ids=target_tokens,
            target_logprobs=target_lps,
        )

        # Build per-candidate results and find best
        candidate_results = []
        best_idx = 0
        best_accepted = -1
        best_logprob_sum = float('-inf')

        for i, (num_accepted, acceptance_mask, corrected_tokens, corrected_logprobs) in enumerate(batch_results):
            # Next token (when all draft tokens accepted)
            next_token_id = 0
            next_token_logprob = 0.0
            if len(target_tokens) > num_accepted:
                next_token_id = target_tokens[num_accepted]
                if target_lps and num_accepted < len(target_lps):
                    token_logprobs = target_lps[num_accepted]
                    if next_token_id in token_logprobs:
                        next_token_logprob = token_logprobs[next_token_id].logprob

            # Compute target logprob sum for accepted tokens (for tie-breaking)
            target_logprob_sum = 0.0
            if target_lps:
                draft_ids = candidates[i]['draft_token_ids']
                for j in range(num_accepted):
                    if j < len(target_lps) and j < len(draft_ids):
                        tid = draft_ids[j]
                        if tid in target_lps[j]:
                            target_logprob_sum += target_lps[j][tid].logprob

            candidate_results.append({
                "num_accepted": num_accepted,
                "acceptance_mask": acceptance_mask,
                "corrected_token_ids": corrected_tokens,
                "corrected_logprobs": corrected_logprobs,
                "next_token_id": next_token_id,
                "next_token_logprob": next_token_logprob,
                "target_logprob_sum": target_logprob_sum,
            })

            # Selection: longest accepted prefix, tie-break by target logprob sum
            if (num_accepted > best_accepted or
                    (num_accepted == best_accepted and target_logprob_sum > best_logprob_sum)):
                best_accepted = num_accepted
                best_logprob_sum = target_logprob_sum
                best_idx = i

        verification_time = (time.time() - start_time) * 1000
        accepted_lengths = [r['num_accepted'] for r in candidate_results]
        print(f"  Multi-candidate result: accepted_lengths={accepted_lengths}, best_idx={best_idx} in {verification_time:.1f}ms")

        return {
            "request_id": request_id,
            "session_id": session_id,
            "candidate_results": candidate_results,
            "best_candidate_idx": best_idx,
            "verification_time_ms": verification_time,
        }

    @modal.method()
    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.8,
        top_k: int = -1,
    ) -> dict:
        """Plain autoregressive generation (baseline, no speculative decoding)."""
        import time
        from vllm import SamplingParams

        start_time = time.time()

        sampling_params = SamplingParams(
            temperature=temperature if temperature > 0 else 0.8,
            top_k=top_k if top_k > 0 else -1,
            top_p=0.95,
            max_tokens=max_tokens,
            seed=42,
        )

        outputs = self.llm.generate(
            prompts=[prompt],
            sampling_params=sampling_params,
            use_tqdm=False,
        )

        output = outputs[0].outputs[0]
        generated_text = self.tokenizer.decode(
            list(self.tokenizer.encode(prompt)) + list(output.token_ids),
            skip_special_tokens=True,
        )
        generation_time = (time.time() - start_time) * 1000

        return {
            "generated_text": generated_text,
            "token_ids": list(output.token_ids),
            "num_tokens": len(output.token_ids),
            "generation_time_ms": generation_time,
        }

    @modal.method()
    def batch_verify(self, requests: list[dict]) -> dict:
        """Batch verification for multiple sequences."""
        import time
        start_time = time.time()

        responses = []
        for req in requests:
            response = self.verify_draft(**req)
            responses.append(response)

        total_time = (time.time() - start_time) * 1000

        return {
            "responses": responses,
            "total_batch_time_ms": total_time,
        }



# --- Convenience entrypoint for direct Modal function calls (no gRPC needed) ---

@app.local_entrypoint()
def main():
    """Test the verification service via Modal's native RPC (no gRPC needed)."""
    service = VerificationService()

    # Simple test: verify some dummy tokens
    result = service.verify_draft.remote(
        request_id="test-001",
        session_id="session-0",
        prefix_token_ids=[1, 2, 3],  # dummy prefix
        draft_token_ids=[4, 5, 6],   # dummy draft
        draft_logprobs=[-0.5, -0.3, -0.8],
        temperature=0.8,
        top_k=50,
    )

    print(f"\nVerification result:")
    print(f"  Accepted: {result['num_accepted_tokens']}/{3}")
    print(f"  Acceptance rate: {result['acceptance_rate']:.1%}")
    print(f"  Time: {result['verification_time_ms']:.1f}ms")
