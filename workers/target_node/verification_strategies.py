"""
Verification strategies for speculative decoding.
Each strategy implements a different approach to accepting/rejecting draft tokens.
"""
import numpy as np
from typing import List, Tuple, Dict, Any


class VerificationStrategy:
    """Base class for verification strategies"""

    def verify(
        self,
        draft_token_ids: List[int],
        draft_logprobs: List[float],
        target_token_ids: List[int],
        target_logprobs: List[Dict[int, Any]],
    ) -> Tuple[int, List[bool], List[int], List[float]]:
        """
        Verify draft tokens against target model output.

        Args:
            draft_token_ids: List of draft token IDs
            draft_logprobs: List of draft token log probabilities
            target_token_ids: List of target token IDs
            target_logprobs: List of dicts mapping token_id -> Logprob object

        Returns:
            Tuple of:
            - num_accepted: Number of accepted tokens
            - acceptance_mask: Boolean mask of accepted tokens
            - corrected_tokens: Token IDs for corrections
            - corrected_logprobs: Log probabilities for corrections
        """
        raise NotImplementedError


class DeterministicVerification(VerificationStrategy):
    """
    Simple deterministic verification: accept if tokens match exactly.
    This should give highest acceptance for same-family models.
    """

    def __init__(self, verbose=True):
        self.verbose = verbose

    def verify(self, draft_token_ids, draft_logprobs, target_token_ids, target_logprobs):
        num_accepted = 0
        acceptance_mask = []
        corrected_tokens = []
        corrected_logprobs = []

        for i, draft_token in enumerate(draft_token_ids):
            if i >= len(target_token_ids):
                break

            target_token = target_token_ids[i]

            if draft_token == target_token:
                # Exact match - accept
                num_accepted += 1
                acceptance_mask.append(True)
                if self.verbose:
                    print(f"    ✓ Token {i}: MATCH (draft={draft_token}, target={target_token})")
            else:
                # Mismatch - reject and correct
                acceptance_mask.append(False)
                corrected_tokens.append(target_token)

                if i < len(target_logprobs) and target_token in target_logprobs[i]:
                    corrected_logprobs.append(target_logprobs[i][target_token].logprob)

                if self.verbose:
                    print(f"    ✗ Token {i}: MISMATCH (draft={draft_token}, target={target_token})")
                break  # Stop after first mismatch

        return num_accepted, acceptance_mask, corrected_tokens, corrected_logprobs


class ProbabilisticVerification(VerificationStrategy):
    """
    Probabilistic verification following SLED paper (Eq. 1):
    α = min(1, p_target(x̃) / p_draft(x̃))
    """

    def __init__(self, verbose=True):
        self.verbose = verbose

    def verify(self, draft_token_ids, draft_logprobs, target_token_ids, target_logprobs):
        num_accepted = 0
        acceptance_mask = []
        corrected_tokens = []
        corrected_logprobs = []

        for i, draft_token in enumerate(draft_token_ids):
            if i >= len(target_token_ids):
                break

            target_token = target_token_ids[i]

            # Fast path: exact match always accepted
            if draft_token == target_token:
                num_accepted += 1
                acceptance_mask.append(True)
                if self.verbose:
                    print(f"    ✓ Token {i}: EXACT MATCH (id={draft_token})")
                continue

            # Probabilistic acceptance for mismatches
            if i >= len(target_logprobs):
                acceptance_mask.append(False)
                corrected_tokens.append(target_token)
                if self.verbose:
                    print(f"    ✗ Token {i}: NO LOGPROBS (draft={draft_token}, target={target_token})")
                break

            target_logprobs_dict = target_logprobs[i]

            # Get probabilities
            if draft_token in target_logprobs_dict:
                p_target = np.exp(target_logprobs_dict[draft_token].logprob)
            else:
                p_target = 1e-10

            if i < len(draft_logprobs):
                p_draft = np.exp(draft_logprobs[i])
            else:
                p_draft = 1e-10

            # Calculate acceptance probability
            alpha = min(1.0, p_target / p_draft)

            if self.verbose:
                print(f"    ? Token {i}: draft={draft_token}, target={target_token}, "
                      f"α={alpha:.4f}, p_t={p_target:.6f}, p_d={p_draft:.6f}")

            # Sample with probability α
            if np.random.random() < alpha:
                num_accepted += 1
                acceptance_mask.append(True)
                if self.verbose:
                    print(f"      → ACCEPTED (probabilistic)")
            else:
                acceptance_mask.append(False)
                corrected_tokens.append(target_token)

                if target_token in target_logprobs_dict:
                    corrected_logprobs.append(target_logprobs_dict[target_token].logprob)

                if self.verbose:
                    print(f"      → REJECTED")
                break

        return num_accepted, acceptance_mask, corrected_tokens, corrected_logprobs


class ThresholdVerification(VerificationStrategy):
    """
    Accept draft token if p_target(draft_token) > threshold.
    This is more lenient than deterministic but doesn't require probabilistic sampling.
    """

    def __init__(self, threshold=0.1, verbose=True):
        self.threshold = threshold
        self.verbose = verbose

    def verify(self, draft_token_ids, draft_logprobs, target_token_ids, target_logprobs):
        num_accepted = 0
        acceptance_mask = []
        corrected_tokens = []
        corrected_logprobs = []

        for i, draft_token in enumerate(draft_token_ids):
            if i >= len(target_token_ids):
                break

            target_token = target_token_ids[i]

            # Fast path: exact match
            if draft_token == target_token:
                num_accepted += 1
                acceptance_mask.append(True)
                if self.verbose:
                    print(f"    ✓ Token {i}: EXACT MATCH (id={draft_token})")
                continue

            # Check if draft token has sufficient probability in target
            if i >= len(target_logprobs):
                acceptance_mask.append(False)
                corrected_tokens.append(target_token)
                break

            target_logprobs_dict = target_logprobs[i]

            if draft_token in target_logprobs_dict:
                p_target = np.exp(target_logprobs_dict[draft_token].logprob)

                if p_target >= self.threshold:
                    # Target model assigns sufficient probability to draft token
                    num_accepted += 1
                    acceptance_mask.append(True)
                    if self.verbose:
                        print(f"    ✓ Token {i}: THRESHOLD ACCEPT (draft={draft_token}, "
                              f"p_target={p_target:.4f} >= {self.threshold})")
                    continue

            # Reject and use target token
            acceptance_mask.append(False)
            corrected_tokens.append(target_token)

            if target_token in target_logprobs_dict:
                corrected_logprobs.append(target_logprobs_dict[target_token].logprob)

            if self.verbose:
                print(f"    ✗ Token {i}: REJECTED (draft={draft_token}, target={target_token})")
            break

        return num_accepted, acceptance_mask, corrected_tokens, corrected_logprobs


class GreedyVerification(VerificationStrategy):
    """
    Always use target model's top token (greedy decoding).
    This effectively disables speculative decoding but is useful for debugging.
    """

    def __init__(self, verbose=True):
        self.verbose = verbose

    def verify(self, draft_token_ids, draft_logprobs, target_token_ids, target_logprobs):
        num_accepted = 0
        acceptance_mask = []
        corrected_tokens = []
        corrected_logprobs = []

        for i, draft_token in enumerate(draft_token_ids):
            if i >= len(target_token_ids):
                break

            target_token = target_token_ids[i]

            if draft_token == target_token:
                num_accepted += 1
                acceptance_mask.append(True)
            else:
                # Always use target token
                acceptance_mask.append(False)
                corrected_tokens.append(target_token)

                if i < len(target_logprobs) and target_token in target_logprobs[i]:
                    corrected_logprobs.append(target_logprobs[i][target_token].logprob)

                if self.verbose:
                    print(f"    → Token {i}: Using target (draft={draft_token}, target={target_token})")
                break

        return num_accepted, acceptance_mask, corrected_tokens, corrected_logprobs


# Registry of available strategies
STRATEGIES = {
    "deterministic": DeterministicVerification,
    "probabilistic": ProbabilisticVerification,
    "threshold": ThresholdVerification,
    "greedy": GreedyVerification,
}


def get_strategy(name: str, **kwargs) -> VerificationStrategy:
    """Get a verification strategy by name"""
    if name not in STRATEGIES:
        raise ValueError(f"Unknown strategy: {name}. Available: {list(STRATEGIES.keys())}")

    return STRATEGIES[name](**kwargs)
