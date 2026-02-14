"""
Frontend Bridge - FastAPI server bridging Next.js frontend to gRPC backend.
Translates HTTP/WebSocket requests into gRPC calls to the draft/target nodes.

Run with --mock to simulate speculative decoding without vLLM/GPU:
    python workers/frontend_bridge/server.py --mock
"""
import asyncio
import json
import random
import time
import uuid
import sys
import os
import argparse

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ── Configuration ──

DRAFT_MODEL = os.getenv("DRAFT_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
VERIFICATION_SERVER = os.getenv("VERIFICATION_SERVER", "localhost:50051")
BRIDGE_PORT = int(os.getenv("BRIDGE_PORT", "8000"))
MOCK_MODE = os.getenv("MOCK_MODE", "").lower() in ("1", "true", "yes")

app = FastAPI(title="SpecNet Frontend Bridge")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Pydantic models ──

class InferenceRequest(BaseModel):
    prompt: str
    max_tokens: int = Field(default=64, ge=1, le=512)
    temperature: float = Field(default=0.8, ge=0.0, le=2.0)
    top_k: int = Field(default=50, ge=-1)
    draft_tokens: int = Field(default=5, ge=1, le=20)

class TokenEvent(BaseModel):
    text: str
    type: str  # "accepted" | "rejected" | "corrected"
    token_id: int = 0
    logprob: float = 0.0

class RoundEvent(BaseModel):
    round_num: int
    drafted: int
    accepted: int
    corrected: int
    verification_time_ms: float
    acceptance_rate: float

class InferenceResponse(BaseModel):
    request_id: str
    generated_text: str
    tokens: list[TokenEvent]
    total_tokens: int
    draft_tokens_generated: int
    draft_tokens_accepted: int
    generation_time_ms: float
    acceptance_rate: float
    speculation_rounds: int

class NodeInfo(BaseModel):
    id: str
    type: str  # "draft" | "target"
    hardware: str
    model: str
    status: str  # "online" | "offline" | "busy"
    latency: float = 0.0
    price: float = 0.0
    gpu_memory: str = ""

class NetworkStats(BaseModel):
    active_draft_nodes: int
    active_target_nodes: int
    total_tps: float
    avg_acceptance_rate: float
    avg_cost_per_1k: float

# ── Mock inference (no GPU required) ──

# Word bank for generating plausible mock responses
MOCK_RESPONSES = {
    "default": (
        "The concept you're asking about is quite fascinating. It involves multiple layers of "
        "understanding that have been refined over decades of research. At its core, the idea "
        "relies on fundamental principles that connect seemingly disparate observations into a "
        "unified framework. Researchers have spent considerable effort developing mathematical "
        "models that capture these relationships with remarkable precision."
    ),
    "relativity": (
        "The theory of relativity, proposed by Albert Einstein in 1905 and 1915, fundamentally "
        "revolutionized our understanding of space and time. Special relativity demonstrates that "
        "the speed of light is constant for all observers, leading to the iconic equation E=mc². "
        "General relativity extends this by describing gravity not as a force, but as a curvature "
        "of spacetime caused by massive objects."
    ),
    "ai": (
        "Artificial intelligence has evolved dramatically since its inception in the 1950s. Modern "
        "deep learning approaches use neural networks with billions of parameters trained on vast "
        "datasets. Techniques like speculative decoding accelerate inference by using a smaller "
        "draft model to predict tokens that a larger target model then verifies, achieving "
        "significant speedups while maintaining output quality."
    ),
    "capital": (
        "The capital city serves as the political and administrative center of the country. It "
        "houses the primary government institutions, diplomatic missions, and often serves as a "
        "cultural hub. The population and economic significance can vary greatly depending on the "
        "nation's structure and historical development."
    ),
}

def _pick_mock_response(prompt: str) -> str:
    prompt_lower = prompt.lower()
    for key, response in MOCK_RESPONSES.items():
        if key != "default" and key in prompt_lower:
            return response
    return MOCK_RESPONSES["default"]

def run_mock_inference(prompt: str, params: InferenceRequest):
    """
    Simulate speculative decoding with realistic timing and token events.
    No GPU, vLLM, or gRPC required.
    """
    request_id = str(uuid.uuid4())[:8]
    response_text = _pick_mock_response(prompt)
    words = response_text.split(" ")
    start_time = time.time()

    all_token_events: list[TokenEvent] = []
    total_draft_generated = 0
    total_draft_accepted = 0
    speculation_rounds = 0

    i = 0
    while i < len(words) and len(all_token_events) < params.max_tokens:
        speculation_rounds += 1
        round_token_events: list[TokenEvent] = []
        round_drafted = 0
        round_accepted = 0
        round_corrected = 0

        # Simulate a draft round of N tokens
        draft_count = min(params.draft_tokens, len(words) - i, params.max_tokens - len(all_token_events))

        for j in range(draft_count):
            word = words[i + j]
            prefix = " " if (i + j) > 0 else ""
            text = prefix + word
            round_drafted += 1
            total_draft_generated += 1

            # ~80% acceptance rate, ~15% rejected+corrected, ~5% just accepted anyway
            roll = random.random()
            if roll < 0.80:
                round_token_events.append(TokenEvent(text=text, type="accepted", logprob=-0.1))
                round_accepted += 1
                total_draft_accepted += 1
            else:
                # Rejected token, then a corrected replacement
                round_token_events.append(TokenEvent(text=text, type="rejected", logprob=-2.5))

                # Pick a plausible correction (synonym-ish)
                corrections = {
                    "fundamentally": "profoundly", "changed": "transformed",
                    "shows": "demonstrates", "famous": "well-known",
                    "explains": "describes", "significant": "notable",
                    "vast": "enormous", "dramatic": "remarkable",
                    "evolved": "progressed", "modern": "contemporary",
                }
                corrected_word = corrections.get(word, word + "s" if not word.endswith("s") else word[:-1])
                round_corrected += 1
                total_draft_generated += 1
                total_draft_accepted += 1
                round_token_events.append(TokenEvent(text=prefix + corrected_word, type="corrected", logprob=-0.3))
                break  # After a rejection, the round ends

        i += draft_count if round_corrected == 0 else (j + 1)  # noqa: F821

        all_token_events.extend(round_token_events)

        # Simulate verification latency
        verify_time = random.uniform(5, 25)
        rate = round_accepted / round_drafted if round_drafted > 0 else 0.0

        round_event = RoundEvent(
            round_num=speculation_rounds,
            drafted=round_drafted,
            accepted=round_accepted,
            corrected=round_corrected,
            verification_time_ms=verify_time,
            acceptance_rate=rate,
        )

        yield ("round", round_event, round_token_events)

        # Small delay to simulate real timing
        time.sleep(random.uniform(0.03, 0.08))

    elapsed = (time.time() - start_time) * 1000
    acceptance_rate = total_draft_accepted / total_draft_generated if total_draft_generated > 0 else 0.0
    generated_text = " ".join(
        te.text.strip() for te in all_token_events if te.type in ("accepted", "corrected")
    )

    summary = InferenceResponse(
        request_id=request_id,
        generated_text=generated_text,
        tokens=all_token_events,
        total_tokens=len(all_token_events),
        draft_tokens_generated=total_draft_generated,
        draft_tokens_accepted=total_draft_accepted,
        generation_time_ms=elapsed,
        acceptance_rate=acceptance_rate,
        speculation_rounds=speculation_rounds,
    )

    yield ("done", summary, [])

# ── Real inference (requires vLLM + GPU + gRPC target) ──

def _get_grpc_stub():
    if not hasattr(_get_grpc_stub, "_channel"):
        import grpc
        _get_grpc_stub._channel = grpc.insecure_channel(VERIFICATION_SERVER)
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'proto'))
        import speculative_decoding_pb2_grpc
        _get_grpc_stub._stub = speculative_decoding_pb2_grpc.VerificationServiceStub(_get_grpc_stub._channel)
    return _get_grpc_stub._stub

def run_real_inference(prompt: str, params: InferenceRequest):
    """
    Run speculative decoding with real vLLM models + gRPC verification.
    Yields (event_type, data, tokens) tuples.
    """
    from vllm import LLM, SamplingParams
    from transformers import AutoTokenizer
    import grpc

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'proto'))
    import common_pb2
    import speculative_decoding_pb2

    if not hasattr(run_real_inference, "_llm"):
        print(f"Loading draft model: {DRAFT_MODEL}")
        run_real_inference._llm = LLM(
            model=DRAFT_MODEL,
            gpu_memory_utilization=0.3,
            max_model_len=4096,
        )
        run_real_inference._tokenizer = AutoTokenizer.from_pretrained(DRAFT_MODEL)
        print("Draft model loaded!")

    llm = run_real_inference._llm
    tokenizer = run_real_inference._tokenizer
    stub = _get_grpc_stub()

    request_id = str(uuid.uuid4())[:8]
    current_text = prompt
    current_token_ids = tokenizer.encode(current_text)
    all_token_events: list[TokenEvent] = []

    total_draft_generated = 0
    total_draft_accepted = 0
    speculation_rounds = 0
    start_time = time.time()

    eos_token_ids = set()
    if getattr(tokenizer, 'eos_token_id', None) is not None:
        eos_token_ids.add(tokenizer.eos_token_id)
    for token in ("<|endoftext|>", "<|im_end|>"):
        if token in tokenizer.get_vocab():
            eos_token_ids.add(tokenizer.convert_tokens_to_ids(token))

    while len(all_token_events) < params.max_tokens:
        speculation_rounds += 1
        num_to_draft = min(params.draft_tokens, params.max_tokens - len(all_token_events))

        sampling_params = SamplingParams(
            temperature=params.temperature,
            top_k=params.top_k if params.top_k > 0 else -1,
            top_p=0.95,
            max_tokens=num_to_draft,
            logprobs=5,
            seed=42,
        )

        outputs = llm.generate(prompts=[current_text], sampling_params=sampling_params, use_tqdm=False)
        draft_output = outputs[0].outputs[0]
        draft_token_ids = draft_output.token_ids
        if not draft_token_ids:
            break

        total_draft_generated += len(draft_token_ids)

        draft_logprobs = []
        if draft_output.logprobs:
            for token_logprobs in draft_output.logprobs:
                token_id = list(token_logprobs.keys())[0]
                draft_logprobs.append(token_logprobs[token_id].logprob)

        try:
            verify_request = speculative_decoding_pb2.VerificationRequest(
                request_id=request_id,
                session_id="session-0",
                prefix_token_ids=current_token_ids,
                draft_token_ids=draft_token_ids,
                draft_logprobs=draft_logprobs,
                temperature=params.temperature,
                top_k=params.top_k if params.top_k > 0 else -1,
            )
            verify_response = stub.VerifyDraft(verify_request)
        except grpc.RpcError as e:
            print(f"gRPC error: {e}")
            break

        num_accepted = verify_response.num_accepted_tokens
        total_draft_accepted += num_accepted

        round_token_events: list[TokenEvent] = []
        eos_reached = False

        for i, tid in enumerate(draft_token_ids):
            text = tokenizer.decode([tid])
            if i < num_accepted:
                round_token_events.append(TokenEvent(text=text, type="accepted", token_id=tid))
                current_token_ids.append(tid)
                if eos_token_ids and tid in eos_token_ids:
                    eos_reached = True
                    break
            else:
                round_token_events.append(TokenEvent(text=text, type="rejected", token_id=tid))
                break

        if not eos_reached and verify_response.corrected_token_ids:
            for j, tid in enumerate(verify_response.corrected_token_ids):
                text = tokenizer.decode([tid])
                round_token_events.append(TokenEvent(
                    text=text, type="corrected", token_id=tid,
                    logprob=verify_response.corrected_logprobs[j] if j < len(verify_response.corrected_logprobs) else 0.0,
                ))
                current_token_ids.append(tid)
                if eos_token_ids and tid in eos_token_ids:
                    eos_reached = True
                    break

        if not eos_reached and eos_token_ids and verify_response.next_token_id in eos_token_ids:
            eos_reached = True

        all_token_events.extend(round_token_events)

        round_event = RoundEvent(
            round_num=speculation_rounds,
            drafted=len(draft_token_ids),
            accepted=num_accepted,
            corrected=len(verify_response.corrected_token_ids),
            verification_time_ms=verify_response.verification_time_ms,
            acceptance_rate=verify_response.acceptance_rate,
        )
        yield ("round", round_event, round_token_events)

        if eos_reached:
            break
        current_text = tokenizer.decode(current_token_ids, skip_special_tokens=True)

    elapsed = (time.time() - start_time) * 1000
    acceptance_rate = total_draft_accepted / total_draft_generated if total_draft_generated > 0 else 0.0
    final_text = run_real_inference._tokenizer.decode(current_token_ids, skip_special_tokens=True)

    summary = InferenceResponse(
        request_id=request_id,
        generated_text=final_text,
        tokens=all_token_events,
        total_tokens=len(all_token_events),
        draft_tokens_generated=total_draft_generated,
        draft_tokens_accepted=total_draft_accepted,
        generation_time_ms=elapsed,
        acceptance_rate=acceptance_rate,
        speculation_rounds=speculation_rounds,
    )
    yield ("done", summary, [])

# ── Dispatch to mock or real ──

def run_inference(prompt: str, params: InferenceRequest):
    if MOCK_MODE:
        yield from run_mock_inference(prompt, params)
    else:
        yield from run_real_inference(prompt, params)

# ── REST endpoints ──

@app.post("/api/inference", response_model=InferenceResponse)
def inference(req: InferenceRequest):
    """Submit a prompt and get the full inference response."""
    result = None
    for event_type, data, _ in run_inference(req.prompt, req):
        if event_type == "done":
            result = data
    return result

@app.websocket("/api/inference/stream")
async def ws_stream_inference(websocket: WebSocket):
    """
    WebSocket endpoint for streaming inference.

    Client sends: {"prompt": "...", "max_tokens": 64, ...}
    Server sends:
      - {"type": "token", "data": {"text": "...", "type": "accepted"}}
      - {"type": "round", "data": {"round_num": 1, "accepted": 3, ...}}
      - {"type": "done", "data": {"request_id": "...", ...}}
    """
    await websocket.accept()
    try:
        raw = await websocket.receive_text()
        params = InferenceRequest(**json.loads(raw))

        loop = asyncio.get_event_loop()

        def _run():
            results = []
            for event_type, data, tokens in run_inference(params.prompt, params):
                results.append((event_type, data, tokens))
            return results

        results = await loop.run_in_executor(None, _run)

        for event_type, data, tokens in results:
            if event_type == "round":
                for token in tokens:
                    await websocket.send_text(json.dumps({
                        "type": "token",
                        "data": token.model_dump(),
                    }))
                await websocket.send_text(json.dumps({
                    "type": "round",
                    "data": data.model_dump(),
                }))
            elif event_type == "done":
                await websocket.send_text(json.dumps({
                    "type": "done",
                    "data": data.model_dump(),
                }))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(json.dumps({
                "type": "error",
                "data": {"message": str(e)},
            }))
        except:
            pass

@app.get("/api/nodes", response_model=list[NodeInfo])
def get_nodes():
    """Return active nodes."""
    mode = "mock" if MOCK_MODE else "live"
    return [
        NodeInfo(
            id="target-0",
            type="target",
            hardware="GPU Server",
            model="Qwen/Qwen2.5-3B-Instruct",
            status="online",
            latency=12,
            price=2.49,
            gpu_memory="80 GB",
        ),
        NodeInfo(
            id="draft-0",
            type="draft",
            hardware="Edge GPU" if not MOCK_MODE else "Mock CPU",
            model=DRAFT_MODEL if not MOCK_MODE else "mock-model",
            status="online",
            latency=45,
            price=0.05,
            gpu_memory="12 GB" if not MOCK_MODE else "N/A",
        ),
    ]

@app.get("/api/stats", response_model=NetworkStats)
def get_stats():
    """Return network-wide statistics."""
    return NetworkStats(
        active_draft_nodes=1,
        active_target_nodes=1,
        total_tps=145 if MOCK_MODE else 0,
        avg_acceptance_rate=0.82 if MOCK_MODE else 0.0,
        avg_cost_per_1k=0.0004,
    )

@app.get("/api/health")
def health():
    return {"status": "ok", "mock": MOCK_MODE}

# ── Startup ──

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SpecNet Frontend Bridge")
    parser.add_argument("--mock", action="store_true", help="Run in mock mode (no GPU/vLLM required)")
    parser.add_argument("--port", type=int, default=BRIDGE_PORT, help="Port to listen on")
    args = parser.parse_args()

    if args.mock:
        MOCK_MODE = True

    print(f"\n{'='*60}")
    print(f"  SpecNet Frontend Bridge")
    print(f"  Port: {args.port}")
    print(f"  Mode: {'MOCK (no GPU)' if MOCK_MODE else 'LIVE (vLLM + gRPC)'}")
    if not MOCK_MODE:
        print(f"  Verification server: {VERIFICATION_SERVER}")
        print(f"  Draft model: {DRAFT_MODEL}")
    print(f"{'='*60}\n")

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=args.port)
