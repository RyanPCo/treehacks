# Speculative Decoding with gRPC

Implementation using the treehacks proto definitions for speculative decoding with vLLM.

## Architecture

```
┌──────────────────────┐         ┌────────────────────────┐
│   Draft Node         │────────>│  Verification Service  │
│  (opt-125m)          │  gRPC   │  (opt-6.7b)           │
│  Client              │ Verify  │  Server                │
│  Drafts tokens       │ Draft   │  Port 50051            │
└──────────────────────┘         └────────────────────────┘
   Generates 5 tokens              Verifies & corrects
   per speculation round           Returns acceptance info
```

## Proto Definitions

Using proto definitions from `treehacks/proto/`:
- **`common.proto`** - Common types (Token, InferenceParams, StatusCode)
- **`speculative_decoding.proto`** - Services and messages
  - `VerificationService` - Runs on target node
  - `DraftNodeService` - API for draft node (not yet implemented as server)

## Services

### VerificationService (Target Node)
Runs the powerful model to verify draft tokens.

**RPCs:**
- `VerifyDraft(VerificationRequest) → VerificationResponse`
- `BatchVerify(BatchVerificationRequest) → BatchVerificationResponse`

**Location:** `target_node/server.py`

### Draft Node Client
Generates draft tokens and coordinates with verification service.

**Location:** `draft_node/client.py`

## Setup

### 1. Prerequisites
```bash
source /home/dgorb/Github/treehacks/.venv/bin/activate
pip install grpcio grpcio-tools transformers vllm
```

### 2. Compile Protos (Already Done ✓)
```bash
cd /home/dgorb/Github/treehacks/treehacks/proto
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. \
    common.proto speculative_decoding.proto
```

This generates:
- `common_pb2.py` & `common_pb2_grpc.py`
- `speculative_decoding_pb2.py` & `speculative_decoding_pb2_grpc.py`

## Usage

### Terminal 1: Start Verification Service (Target Node)

```bash
cd /home/dgorb/Github/treehacks/treehacks/workers
./start_target_server.sh
```

**Output:**
```
🎯 Verification Service (Target Node) started on port 50051
   Model: facebook/opt-6.7b
   Ready to verify draft tokens from draft nodes
```

### Terminal 2: Run Draft Node Client

```bash
cd /home/dgorb/Github/treehacks/treehacks/workers
./start_draft_client.sh
```

**Output:**
```
📝 Draft Node Client - Speculative Decoding Demo
🚀 Starting inference...
  Round 1: Drafted 5 tokens in 45.2ms
    Draft: ' John and I am a student'
    Verified: 3/5 accepted (60.0%)
    Corrected: +1 tokens from target
✅ Inference complete!
```

## Message Flow

```
Draft Node                          Verification Service
──────────                          ────────────────────

1. Generate 5 draft tokens
   (using opt-125m)

2. VerificationRequest ────────────>
   - prefix_token_ids
   - draft_token_ids [5 tokens]
   - draft_logprobs
   - temperature, top_k

                                    3. Generate own tokens
                                       (using opt-6.7b)

                                    4. Compare draft vs target
                                       - Count accepted
                                       - Generate correction

                    <────────────── 5. VerificationResponse
                                       - num_accepted_tokens: 3
                                       - corrected_token_ids: [1 token]
                                       - acceptance_rate: 60%

6. Accept 3 tokens + 1 correction
7. Update context
8. Repeat until max_tokens
```

## Configuration

### Target Node (`target_node/server.py`)
```python
VerificationServiceImpl(
    model_name="facebook/opt-6.7b"  # Change model here
)

# In serve():
serve(port=50051)  # Change port here
```

**GPU Memory:** 60% (adjustable via `gpu_memory_utilization`)

### Draft Node (`draft_node/client.py`)
```python
DraftNodeClient(
    draft_model="facebook/opt-125m",      # Change draft model
    verification_server="localhost:50051", # Change server address
    num_draft_tokens=5,                    # Tokens per round
)
```

**GPU Memory:** 30% (adjustable via `gpu_memory_utilization`)

## Proto Message Types

### InferenceJobRequest
```protobuf
message InferenceJobRequest {
  string request_id = 1;
  string prompt = 2;
  InferenceParams params = 3;
  string model_id = 4;
  int64 timestamp = 5;
}
```

### VerificationRequest
```protobuf
message VerificationRequest {
  string request_id = 1;
  repeated int32 prefix_token_ids = 3;
  repeated int32 draft_token_ids = 4;
  repeated float draft_logprobs = 5;
  float temperature = 6;
  int32 top_k = 7;
}
```

### VerificationResponse
```protobuf
message VerificationResponse {
  int32 num_accepted_tokens = 3;
  repeated bool acceptance_mask = 4;
  repeated int32 corrected_token_ids = 5;
  int32 next_token_id = 7;
  float acceptance_rate = 10;
}
```

## Performance Metrics

The system tracks detailed metrics:

**Draft Node:**
- `total_tokens` - Total generated tokens
- `draft_tokens_generated` - Total drafted (before verification)
- `draft_tokens_accepted` - Total accepted by target
- `acceptance_rate` - % of draft tokens accepted
- `speculation_rounds` - Number of draft-verify cycles
- `generation_time_ms` - Total time
- `tokens_per_second` - Overall speed

**Verification Service:**
- `verification_time_ms` - Time to verify each batch
- `acceptance_rate` - Per-request acceptance rate

## Expected Performance

| Acceptance Rate | Speedup | Model Similarity |
|----------------|---------|------------------|
| > 70%          | 2-3x    | Excellent - Same family, similar size |
| 50-70%         | 1.5-2x  | Good - Same family (OPT + OPT) |
| 30-50%         | 1.2-1.5x| Fair - Different families |
| < 30%          | <1.2x   | Poor - Incompatible models |

## Example Output

```
🚀 Starting inference for request: req-1234
   Prompt: 'The capital of France is'
   Max tokens: 16
   Draft tokens/round: 5

  Round 1: Drafted 5 tokens in 42.3ms
    Draft: ' Paris, and the city is'
    Verified: 5/5 accepted (100.0%)

  Round 2: Drafted 5 tokens in 38.1ms
    Draft: ' home to many famous landmarks'
    Verified: 4/5 accepted (80.0%)
    Corrected: +1 tokens from target

  Round 3: Drafted 5 tokens in 41.2ms
    Draft: ' including the Eiffel Tower and'
    Verified: 2/5 accepted (40.0%)
    Corrected: +1 tokens from target

✅ Inference complete!
   Total tokens: 16
   Draft generated: 15
   Draft accepted: 11 (73.3%)
   Speculation rounds: 3
   Total time: 892.3ms (17.9 tokens/sec)
   Result: 'The capital of France is Paris, and the city is home to many famous landmarks...'
```

## File Structure

```
treehacks/
├── proto/
│   ├── common.proto                      # Common types
│   ├── common_pb2.py                     # Generated
│   ├── common_pb2_grpc.py               # Generated
│   ├── speculative_decoding.proto        # Service definitions
│   ├── speculative_decoding_pb2.py      # Generated
│   └── speculative_decoding_pb2_grpc.py # Generated
│
└── workers/
    ├── README.md                         # This file
    ├── start_target_server.sh           # Target launcher
    ├── start_draft_client.sh            # Draft launcher
    │
    ├── target_node/
    │   └── server.py                    # VerificationService impl
    │
    └── draft_node/
        └── client.py                    # Draft client with spec decoding
```

## Troubleshooting

### Import Errors
If you see `ModuleNotFoundError: No module named 'common_pb2'`:
```bash
cd /home/dgorb/Github/treehacks/treehacks/proto
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. \
    common.proto speculative_decoding.proto
```

### Connection Failed
- Ensure target server is running first
- Check port 50051 is not blocked
- Verify server shows "Verification service ready!"

### Low Acceptance Rate
- Use models from same family (both OPT, both Llama, etc.)
- Reduce temperature for more deterministic generation
- Try smaller `num_draft_tokens` (3-4 instead of 5)

### Out of Memory
- Reduce `gpu_memory_utilization` (target: 0.5, draft: 0.25)
- Use smaller models
- Run on separate GPUs if available

## Advanced: Batch Verification

The proto supports batch verification for efficiency:

```python
# In draft node (future enhancement)
requests = [...]  # Multiple VerificationRequest objects

batch_request = speculative_decoding_pb2.BatchVerificationRequest(
    requests=requests,
    max_batch_size=8,
)

batch_response = verification_stub.BatchVerify(batch_request)
```

This allows verifying multiple draft sequences in one call, improving throughput.

## Next Steps

1. **Implement DraftNodeService as gRPC Server**
   - Currently draft node only has client
   - Add server to receive InferenceJobRequest from router

2. **Session Management**
   - Implement KV cache reuse across requests
   - Use `session_id` for stateful inference

3. **Streaming Support**
   - Implement `StreamInference` RPC
   - Send tokens as they're generated

4. **Router Integration**
   - Connect to router service
   - Handle job distribution

5. **Metrics & Monitoring**
   - Add Prometheus metrics
   - Track acceptance rates over time
   - Monitor GPU utilization
