#!/usr/bin/env python3
"""
GSM8K / HumanEval Benchmark for Speculative Decoding

Tests the draft→target speculative decoding system on:
- GSM8K: grade school math questions
- HumanEval: Python code completion (use --humaneval flag)

Measures acceptance rate, speed, and correctness.
"""
import sys
import os
import time
import json
import argparse
from typing import List, Dict

# Add proto directory to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'proto'))

import common_pb2
import speculative_decoding_pb2
from draft_node.client import DraftNodeClient


# Sample GSM8K questions (you can expand this or load from HuggingFace datasets)
GSM8K_SAMPLES = [
    {
        "question": "Natalia sold clips to 48 of her friends in April, and then she sold half as many clips in May. How many clips did Natalia sell altogether in April and May?",
        "answer": "72"
    },
    {
        "question": "Weng earns $12 an hour for babysitting. Yesterday, she just did 50 minutes of babysitting. How much did she earn?",
        "answer": "10"
    },
    {
        "question": "Betty is saving money for a new wallet which costs $100. Betty has only half of the money she needs. Her parents decided to give her $15 for that purpose, and her grandparents twice as much as her parents. How much more money does Betty need to buy the wallet?",
        "answer": "5"
    },
    {
        "question": "Julie is reading a 120-page book. Yesterday, she was able to read 12 pages and today, she read twice as many pages as yesterday. If she wants to read half of the remaining pages tomorrow, how many pages should she read?",
        "answer": "42"
    },
    {
        "question": "James writes a 3-page letter to 2 different friends twice a week. How many pages does he write a year?",
        "answer": "624"
    },
    {
        "question": "Mark has a garden with flowers. He planted plants of three different colors in it. Ten of them are yellow, and there are 80% more of those in purple. There are only 25% as many green flowers as there are yellow and purple flowers. How many flowers does Mark have in his garden?",
        "answer": "35"
    },
    {
        "question": "Albert is wondering how much pizza he can eat in one day. He buys 2 large pizzas and 2 small pizzas. A large pizza has 16 slices and a small pizza has 8 slices. If he eats it all, how many pieces does he eat that day?",
        "answer": "48"
    },
    {
        "question": "Ken created a care package to send to his brother, who was away at boarding school. Ken placed a box on a scale, and then he poured into the box enough jelly beans to bring the weight to 2 pounds. Then, he added enough brownies to cause the weight to triple. Next, he added another 2 pounds of jelly beans. And finally, he added enough gummy worms to double the weight once again. What was the final weight of the box of goodies, in pounds?",
        "answer": "16"
    },
    {
        "question": "Alexis is applying for a new job and bought a new set of business clothes to wear to the interview. She went to a department store with a budget of $200 and spent $30 on a button-up shirt, $46 on suit pants, $38 on a suit coat, $11 on socks, and $18 on a belt. She also purchased a pair of shoes, but lost the receipt for them. She has $16 left from her budget. How much did Alexis pay for the shoes?",
        "answer": "41"
    },
    {
        "question": "Tina makes $18.00 an hour. If she works more than 8 hours per shift, she is eligible for overtime, which is paid by her hourly wage + 1/2 her hourly wage. If she works 10 hours every day for 5 days, how much money does she make?",
        "answer": "990"
    },
]

# Sample HumanEval problems (code completion tasks)
HUMANEVAL_SAMPLES = [
    {
        "task_id": "HumanEval/0",
        "prompt": 'def has_close_elements(numbers: List[float], threshold: float) -> bool:\n    """ Check if in given list of numbers, are any two numbers closer to each other than\n    given threshold.\n    >>> has_close_elements([1.0, 2.0, 3.0], 0.5)\n    False\n    >>> has_close_elements([1.0, 2.8, 3.0, 4.0, 5.0, 2.0], 0.3)\n    True\n    """\n',
        "entry_point": "has_close_elements",
        "canonical_solution": "    for idx, elem in enumerate(numbers):\n        for idx2, elem2 in enumerate(numbers):\n            if idx != idx2:\n                distance = abs(elem - elem2)\n                if distance < threshold:\n                    return True\n    return False\n",
    },
    {
        "task_id": "HumanEval/1",
        "prompt": 'def separate_paren_groups(paren_string: str) -> List[str]:\n    """ Input string is valid parentheses string containing only "(",")". Split\n    it into list of string where each string is one group of balanced parentheses.\n    >>> separate_paren_groups("( ) (( )) (( )( ))") \n    ["()", "(())", "(()())"]\n    """\n',
        "entry_point": "separate_paren_groups",
        "canonical_solution": "    result = []\n    current_string = []\n    current_depth = 0\n    for c in paren_string:\n        if c == \'(\':\n            current_depth += 1\n            current_string.append(c)\n        elif c == \')\':\n            current_depth -= 1\n            current_string.append(c)\n            if current_depth == 0:\n                result.append(\'\'.join(current_string))\n                current_string.clear()\n    return result\n",
    },
    {
        "task_id": "HumanEval/2",
        "prompt": 'def truncate_number(n: float) -> float:\n    """ Return the first positive number that can be obtained by repeatedly summing the digits of n.\n    >>> truncate_number(1234)\n    1\n    >>> truncate_number(0.0)\n    0\n    """\n',
        "entry_point": "truncate_number",
        "canonical_solution": "    if n == 0:\n        return 0\n    return n - int(n)\n",
    },
]


def load_gsm8k_from_hf(num_samples=50):
    """Load GSM8K dataset from HuggingFace"""
    try:
        from datasets import load_dataset

        print("Loading GSM8K dataset from HuggingFace...")
        dataset = load_dataset("gsm8k", "main", split="test")

        samples = []
        for i, item in enumerate(dataset):
            if i >= num_samples:
                break

            # Extract answer from the solution (last number)
            answer_text = item['answer'].split("####")[-1].strip()

            samples.append({
                "question": item['question'],
                "answer": answer_text,
            })

        print(f"Loaded {len(samples)} questions from HuggingFace GSM8K")
        return samples

    except ImportError:
        print("⚠ HuggingFace datasets not installed. Using built-in samples.")
        print("  To use full dataset: pip install datasets")
        return GSM8K_SAMPLES[:num_samples]
    except Exception as e:
        print(f"⚠ Error loading from HuggingFace: {e}")
        print("  Falling back to built-in samples.")
        return GSM8K_SAMPLES[:num_samples]


def load_humaneval_from_hf(num_samples=50):
    """Load HumanEval dataset from HuggingFace"""
    try:
        from datasets import load_dataset

        print("Loading HumanEval dataset from HuggingFace...")
        dataset = load_dataset("openai/openai_humaneval", split="test")

        samples = []
        for i, item in enumerate(dataset):
            if i >= num_samples:
                break
            samples.append({
                "task_id": item["task_id"],
                "prompt": item["prompt"],
                "entry_point": item["entry_point"],
                "canonical_solution": item["canonical_solution"],
                "test": item.get("test", ""),
            })

        print(f"Loaded {len(samples)} problems from HuggingFace HumanEval")
        return samples

    except ImportError:
        print("⚠ HuggingFace datasets not installed. Using built-in samples.")
        print("  To use full dataset: pip install datasets")
        return HUMANEVAL_SAMPLES[:num_samples]
    except Exception as e:
        print(f"⚠ Error loading from HuggingFace: {e}")
        print("  Falling back to built-in samples.")
        return HUMANEVAL_SAMPLES[:num_samples]


def run_benchmark(
    draft_model="Qwen/Qwen2.5-1.5B-Instruct",
    target_model="Qwen/Qwen2.5-3B-Instruct",
    verification_server="localhost:50051",
    num_samples=10,
    max_tokens=512,
    temperature=0.0,
    use_hf_dataset=False,
    humaneval=False,
):
    """Run benchmark (GSM8K or HumanEval)"""

    benchmark_name = "HumanEval" if humaneval else "GSM8K"
    print("\n" + "="*100)
    print(f"{benchmark_name} BENCHMARK - Speculative Decoding Performance Test")
    print("="*100)
    print(f"\nConfiguration:")
    print(f"  Dataset: {benchmark_name}")
    print(f"  Draft Model: {draft_model}")
    print(f"  Target Model: {target_model} (via verification server)")
    print(f"  Samples: {num_samples}")
    print(f"  Max Tokens: {max_tokens}")
    print(f"  Temperature: {temperature}")
    print(f"  Data Source: {'HuggingFace' if use_hf_dataset else 'Built-in samples'}")
    print("="*100 + "\n")

    # Load dataset
    if humaneval:
        if use_hf_dataset:
            questions = load_humaneval_from_hf(num_samples)
        else:
            questions = HUMANEVAL_SAMPLES[:num_samples]
    else:
        if use_hf_dataset:
            questions = load_gsm8k_from_hf(num_samples)
        else:
            questions = GSM8K_SAMPLES[:num_samples]

    # Initialize client
    print("Initializing draft node client...")
    client = DraftNodeClient(
        draft_model=draft_model,
        verification_server=verification_server,
        num_draft_tokens=5,
    )

    # Run benchmark
    results = []
    total_start_time = time.time()

    for i, item in enumerate(questions):
        print(f"\n{'─'*100}")
        print(f"Question {i+1}/{len(questions)}")
        print(f"{'─'*100}")

        if humaneval:
            task_id = item.get("task_id", f"humaneval-{i}")
            prompt_text = item["prompt"]
            expected = item.get("canonical_solution", "")
            print(f"Task: {task_id}")
            print(f"Prompt: {prompt_text[:150]}...")
            print(f"Expected (canonical): {expected[:100]}...")
            model_prompt = f"Complete the following Python function. Output only the function body completion, no explanation.\n\n{prompt_text}"
            request_id = f"humaneval-{i}"
        else:
            print(f"Q: {item['question']}")
            print(f"Expected answer: {item['answer']}")
            model_prompt = f"Question: {item['question']}\n\nAnswer: Let's solve this step by step.\n"
            request_id = f"gsm8k-{i}"
        print()

        # Create request
        request = speculative_decoding_pb2.InferenceJobRequest(
            request_id=request_id,
            prompt=model_prompt,
            params=common_pb2.InferenceParams(
                max_tokens=max_tokens,
                temperature=temperature,
                top_k=-1 if temperature == 0 else 50,
                draft_tokens=5,
            ),
            model_id=target_model,
            timestamp=int(time.time() * 1000),
        )

        # Execute inference
        start_time = time.time()
        response = client.execute_inference(request)
        elapsed = time.time() - start_time

        # Store results
        if humaneval:
            result = {
                'question_num': i + 1,
                'task_id': item.get("task_id", f"humaneval-{i}"),
                'prompt': item['prompt'],
                'canonical_solution': item.get('canonical_solution', ''),
                'generated_text': response.generated_text,
            }
        else:
            result = {
                'question_num': i + 1,
                'question': item['question'],
                'expected_answer': item['answer'],
                'generated_text': response.generated_text,
            }
        result.update({
            'total_tokens': response.total_tokens,
            'draft_generated': response.draft_tokens_generated,
            'draft_accepted': response.draft_tokens_accepted,
            'acceptance_rate': response.acceptance_rate,
            'speculation_rounds': response.speculation_rounds,
            'generation_time_ms': response.generation_time_ms,
            'wall_time_seconds': elapsed,
            'tokens_per_sec': response.total_tokens / (response.generation_time_ms / 1000) if response.generation_time_ms > 0 else 0,
        })
        results.append(result)

        # Print summary for this question
        print(f"Generated: {response.generated_text[:200]}...")
        print(f"\n📊 Stats:")
        print(f"   Time: {elapsed:.1f}s ({result['tokens_per_sec']:.1f} tokens/sec)")
        print(f"   Acceptance: {response.acceptance_rate:.1%} ({response.draft_tokens_accepted}/{response.draft_tokens_generated})")
        print(f"   Tokens: {response.total_tokens}")
        print(f"   Rounds: {response.speculation_rounds}")

        # Small delay to prevent overload
        time.sleep(0.5)

    total_elapsed = time.time() - total_start_time

    # Calculate aggregate statistics
    print("\n" + "="*100)
    print("BENCHMARK RESULTS")
    print("="*100)

    avg_acceptance = sum(r['acceptance_rate'] for r in results) / len(results)
    avg_speed = sum(r['tokens_per_sec'] for r in results) / len(results)
    avg_time_per_question = sum(r['wall_time_seconds'] for r in results) / len(results)
    total_tokens = sum(r['total_tokens'] for r in results)
    total_draft_generated = sum(r['draft_generated'] for r in results)
    total_draft_accepted = sum(r['draft_accepted'] for r in results)
    total_rounds = sum(r['speculation_rounds'] for r in results)

    print(f"\n📈 Overall Performance:")
    print(f"   Average Acceptance Rate: {avg_acceptance:.1%}")
    print(f"   Total Tokens Generated: {total_tokens}")
    print(f"   Total Draft Generated: {total_draft_generated}")
    print(f"   Total Draft Accepted: {total_draft_accepted}")
    print(f"   Overall Acceptance: {total_draft_accepted/total_draft_generated:.1%}" if total_draft_generated > 0 else "   Overall Acceptance: N/A")
    print(f"   Average Speed: {avg_speed:.1f} tokens/sec")
    print(f"   Total Speculation Rounds: {total_rounds}")
    print(f"\n⏱️  Timing:")
    print(f"   Total Benchmark Time: {total_elapsed:.1f}s")
    print(f"   Average per Question: {avg_time_per_question:.1f}s")
    print(f"   Questions Processed: {len(results)}")

    print(f"\n📊 Per-Question Breakdown:")
    print(f"{'Q#':<5} {'Time':<10} {'Tokens':<8} {'Accept%':<10} {'Speed':<12} {'Rounds':<8}")
    print("─" * 65)
    for r in results:
        print(f"{r['question_num']:<5} {r['wall_time_seconds']:>6.1f}s   {r['total_tokens']:<8} {r['acceptance_rate']:>6.1%}    {r['tokens_per_sec']:>8.1f}/s    {r['speculation_rounds']:<8}")

    # Distribution analysis
    print(f"\n📉 Acceptance Rate Distribution:")
    ranges = [
        (0, 25, "Very Low (0-25%)"),
        (25, 50, "Low (25-50%)"),
        (50, 75, "Medium (50-75%)"),
        (75, 90, "High (75-90%)"),
        (90, 100, "Very High (90-100%)"),
    ]
    for min_r, max_r, label in ranges:
        count = sum(1 for r in results if min_r <= r['acceptance_rate'] * 100 < max_r)
        if count > 0:
            print(f"   {label}: {count} questions ({count/len(results)*100:.1f}%)")

    # Save results to logs folder
    script_dir = os.path.dirname(os.path.abspath(__file__))
    logs_dir = os.path.join(script_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    output_prefix = "humaneval" if humaneval else "gsm8k"
    output_file = os.path.join(logs_dir, f"{output_prefix}_benchmark_{int(time.time())}.json")
    with open(output_file, 'w') as f:
        json.dump({
            'config': {
                'dataset': benchmark_name,
                'draft_model': draft_model,
                'target_model': target_model,
                'num_samples': num_samples,
                'max_tokens': max_tokens,
                'temperature': temperature,
            },
            'summary': {
                'avg_acceptance_rate': avg_acceptance,
                'avg_speed': avg_speed,
                'avg_time_per_question': avg_time_per_question,
                'total_tokens': total_tokens,
                'total_draft_generated': total_draft_generated,
                'total_draft_accepted': total_draft_accepted,
                'total_time': total_elapsed,
                'num_questions': len(results),
            },
            'results': results,
        }, f, indent=2)

    print(f"\n💾 Results saved to: {output_file}")
    print("="*100 + "\n")

    # Cleanup
    del client


def main():
    parser = argparse.ArgumentParser(description='GSM8K / HumanEval Benchmark for Speculative Decoding')
    parser.add_argument('--humaneval', action='store_true',
                        help='Use HumanEval code completion dataset instead of GSM8K')
    parser.add_argument('--draft-model', type=str, default='Qwen/Qwen2.5-1.5B-Instruct',
                        help='Draft model to use (default: Qwen/Qwen2.5-1.5B-Instruct)')
    parser.add_argument('--target-model', type=str, default='Qwen/Qwen2.5-3B-Instruct',
                        help='Target model (on server) (default: Qwen/Qwen2.5-3B-Instruct)')
    parser.add_argument('--server', type=str, default='localhost:50051',
                        help='Verification server address (default: localhost:50051)')
    parser.add_argument('--num-samples', type=int, default=10,
                        help='Number of questions to test (default: 10)')
    parser.add_argument('--max-tokens', type=int, default=512,
                        help='Maximum tokens to generate per question (default: 512)')
    parser.add_argument('--temperature', type=float, default=0.0,
                        help='Sampling temperature (default: 0.0 for greedy)')
    parser.add_argument('--use-hf', action='store_true',
                        help='Load dataset from HuggingFace (requires: pip install datasets)')

    args = parser.parse_args()

    run_benchmark(
        draft_model=args.draft_model,
        target_model=args.target_model,
        verification_server=args.server,
        num_samples=args.num_samples,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        use_hf_dataset=args.use_hf,
        humaneval=args.humaneval,
    )


if __name__ == '__main__':
    main()
