# GSM8K / HumanEval Benchmark Usage Guide

## Quick Start

```bash
# Make sure target server is running
./start_target_server.sh --strategy deterministic

# Run GSM8K benchmark with 10 questions (default)
python benchmark_gsm8k.py

# Run HumanEval code completion benchmark
python benchmark_gsm8k.py --humaneval

# Run with more questions
python benchmark_gsm8k.py --num-samples 50

# Use HuggingFace dataset (requires: pip install datasets)
python benchmark_gsm8k.py --num-samples 50 --use-hf

# HumanEval with full dataset from HuggingFace
python benchmark_gsm8k.py --humaneval --use-hf --num-samples 50
```

## What It Measures

The benchmark tests speculative decoding on grade school math questions (GSM8K dataset):

### Key Metrics

1. **Acceptance Rate** - % of draft tokens accepted by target model
   - Higher = better speculation efficiency
   - Target: >80% for same-family models

2. **Tokens Per Second** - Generation speed
   - Includes both draft and verification time
   - Compare against baseline (target model alone)

3. **Draft Efficiency** - Total draft accepted / total draft generated
   - Shows overall speculation effectiveness

4. **Speculation Rounds** - Number of draft→verify cycles
   - More rounds with high acceptance = good
   - Many rounds with low acceptance = inefficient

### Output

#### Console Output
- Real-time progress for each question
- Per-question statistics
- Aggregate performance summary
- Acceptance rate distribution

#### JSON File
Saved as `gsm8k_benchmark_<timestamp>.json`:
```json
{
  "config": {
    "draft_model": "facebook/opt-350m",
    "target_model": "facebook/opt-1.3b",
    "num_samples": 10,
    "max_tokens": 512,
    "temperature": 0.0
  },
  "summary": {
    "avg_acceptance_rate": 0.852,
    "avg_speed": 66.1,
    "total_tokens": 5120,
    "total_draft_generated": 5733,
    "total_draft_accepted": 4845
  },
  "results": [...]
}
```

## Example Results

### With OPT-350m → OPT-1.3b (Recommended)

```
📈 Overall Performance:
   Average Acceptance Rate: 85.2%
   Total Tokens Generated: 1536
   Total Draft Generated: 1733
   Total Draft Accepted: 1465
   Overall Acceptance: 84.5%
   Average Speed: 66.1 tokens/sec
   Total Speculation Rounds: 348

📉 Acceptance Rate Distribution:
   Medium (50-75%): 1 questions (33.3%)
   High (75-90%): 1 questions (33.3%)
   Very High (90-100%): 1 questions (33.3%)
```

### With OPT-125m → OPT-1.3b (Not Recommended)

```
📈 Overall Performance:
   Average Acceptance Rate: 42.3%
   Total Tokens Generated: 1536
   Total Draft Generated: 2841
   Total Draft Accepted: 1201
   Overall Acceptance: 42.3%
   Average Speed: 38.2 tokens/sec
```

## Command-Line Options

```bash
python benchmark_gsm8k.py [OPTIONS]

Options:
  --humaneval              Use HumanEval code completion dataset instead of GSM8K
  --draft-model TEXT       Draft model (default: Qwen/Qwen2.5-1.5B-Instruct)
  --target-model TEXT      Target model (default: Qwen/Qwen2.5-3B-Instruct)
  --server TEXT            Verification server address (default: localhost:50051)
  --num-samples INTEGER    Number of questions to test (default: 10)
  --max-tokens INTEGER     Max tokens per question (default: 512)
  --temperature FLOAT      Sampling temperature (default: 0.0)
  --use-hf                 Load from HuggingFace (requires datasets package)
```

### Examples

```bash
# Test different draft models
python benchmark_gsm8k.py --draft-model facebook/opt-125m --num-samples 5
python benchmark_gsm8k.py --draft-model facebook/opt-350m --num-samples 5

# Test with sampling (temperature > 0)
python benchmark_gsm8k.py --temperature 0.5 --num-samples 10

# Full benchmark with HuggingFace dataset
pip install datasets
python benchmark_gsm8k.py --use-hf --num-samples 100

# Quick test (3 questions)
python benchmark_gsm8k.py --num-samples 3
```

## Interpreting Results

### Acceptance Rate

| Range | Interpretation | Action |
|-------|----------------|--------|
| >90% | Excellent | Models well-matched, speculation very effective |
| 75-90% | Good | Decent speedup, this is expected for OPT-350m→1.3b |
| 50-75% | Fair | Some benefit but could improve |
| <50% | Poor | Draft model too small or different family |

### Speed (Tokens/Sec)

Compare against baseline (target model without speculation):
- **Baseline OPT-1.3b:** ~40-50 tokens/sec
- **With speculation (OPT-350m):** ~60-70 tokens/sec
- **Speedup:** ~1.4-1.5x

Expected speedup formula:
```
Speedup ≈ 1 + (acceptance_rate × draft_speed_ratio)

Where draft_speed_ratio = (speed_draft - speed_target) / speed_target
```

### Per-Question Variance

It's normal to see variance across questions:
- Easy questions: Higher acceptance (model agreement)
- Open-ended questions: Lower acceptance (more creativity)
- Math reasoning: Medium-high acceptance (structured)

## Troubleshooting

### Low Acceptance Rate (<50%)

**Check:**
1. Are you using compatible models? (both OPT family)
2. Is draft model large enough? (opt-350m minimum)
3. Using greedy decoding? (temperature=0)
4. Server running with correct strategy?

**Try:**
```bash
# Restart server with verbose logging
./start_target_server.sh --strategy deterministic --verbose

# Run small benchmark
python benchmark_gsm8k.py --num-samples 3
```

### Slow Performance

**Check:**
1. GPU memory usage (might be swapping)
2. Number of speculation rounds (too many = overhead)
3. Draft model size (larger = slower)

**Try:**
```bash
# Reduce max tokens for faster testing
python benchmark_gsm8k.py --max-tokens 256 --num-samples 5
```

### Out of Memory

**Solutions:**
1. Reduce `gpu_memory_utilization` in server.py and client.py
2. Use smaller models
3. Reduce `max_tokens` parameter

## Comparing Configurations

To compare different setups, run multiple benchmarks:

```bash
# Test 1: OPT-125m (baseline - small draft)
python benchmark_gsm8k.py --draft-model facebook/opt-125m --num-samples 10

# Test 2: OPT-350m (recommended)
python benchmark_gsm8k.py --draft-model facebook/opt-350m --num-samples 10

# Test 3: With sampling
python benchmark_gsm8k.py --temperature 0.5 --num-samples 10

# Test 4: Different verification strategy
# (restart server with --strategy probabilistic)
./start_target_server.sh --strategy probabilistic
python benchmark_gsm8k.py --num-samples 10
```

Then compare the JSON output files to see which configuration performs best.

## Best Practices

1. **Use greedy decoding (temp=0)** for best acceptance rates
2. **Start with 10 samples** for quick validation
3. **Use HuggingFace dataset** for comprehensive benchmarks
4. **Save JSON results** for later comparison
5. **Test multiple draft models** to find optimal speedup/accuracy tradeoff
6. **Compare against baseline** (target model alone) to measure actual speedup

## What's Next

After benchmarking:

1. **Found good settings?** Update default config in client.py
2. **Want faster?** Try smaller draft model (but watch acceptance rate)
3. **Need better quality?** Use larger target model
4. **Production deployment?** Add batch processing and caching
