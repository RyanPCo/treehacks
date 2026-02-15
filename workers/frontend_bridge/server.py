"""
Frontend Bridge - FastAPI server bridging Next.js frontend to Modal backend.
Translates HTTP/WebSocket requests into calls to draft/target nodes.

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

import grpc
import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ── Configuration ──

DRAFT_MODEL = os.getenv("DRAFT_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
BRIDGE_PORT = int(os.getenv("BRIDGE_PORT", "8000"))
MOCK_MODE = os.getenv("MOCK_MODE", "").lower() in ("1", "true", "yes")
TOKEN_SEND_BATCH_SIZE = max(1, int(os.getenv("TOKEN_SEND_BATCH_SIZE", "1")))
DEFAULT_MAX_TOKENS = int(os.getenv("DEFAULT_MAX_TOKENS", "512"))
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "You are a helpful AI assistant.")
PROMPT_FORMAT = os.getenv("PROMPT_FORMAT", "chatml").lower()
ROUTER_ADDRESS = os.getenv("ROUTER_ADDRESS", "").strip()
ROUTER_GRPC_TIMEOUT_SECONDS = float(os.getenv("ROUTER_GRPC_TIMEOUT_SECONDS", "5"))
DRAFT_NODE_GRPC_TIMEOUT_SECONDS = float(os.getenv("DRAFT_NODE_GRPC_TIMEOUT_SECONDS", "600"))

PROTO_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "proto",
)
if PROTO_DIR not in sys.path:
    sys.path.insert(0, PROTO_DIR)


def _router_base_url() -> str:
    if not ROUTER_ADDRESS:
        return ""
    if ROUTER_ADDRESS.startswith("http://") or ROUTER_ADDRESS.startswith("https://"):
        return ROUTER_ADDRESS.rstrip("/")
    return f"http://{ROUTER_ADDRESS.rstrip('/')}"

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
    max_tokens: int = Field(default=DEFAULT_MAX_TOKENS, ge=1, le=4096)
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


def _build_model_prompt(user_prompt: str) -> str:
    """Build a model prompt with a global system message."""
    system_prompt = SYSTEM_PROMPT.strip()
    if not system_prompt:
        return user_prompt

    if PROMPT_FORMAT == "plain":
        return f"System: {system_prompt}\nUser: {user_prompt}\nAssistant:"

    # ChatML format works well for Qwen instruct models.
    return (
        f"<|im_start|>system\n{system_prompt}\n<|im_end|>\n"
        f"<|im_start|>user\n{user_prompt}\n<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )

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
    output_token_count = 0
    while i < len(words) and output_token_count < params.max_tokens:
        speculation_rounds += 1
        round_token_events: list[TokenEvent] = []
        round_drafted = 0
        round_accepted = 0
        round_corrected = 0

        # Simulate a draft round of N tokens
        draft_count = min(params.draft_tokens, len(words) - i, params.max_tokens - output_token_count)

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
                output_token_count += 1
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
                output_token_count += 1
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

# ── Real inference (delegated to router + draft nodes) ──


def _build_inference_job_request(prompt: str, params: InferenceRequest, request_id: str):
    import common_pb2
    import speculative_decoding_pb2

    model_prompt = _build_model_prompt(prompt)
    return speculative_decoding_pb2.InferenceJobRequest(
        request_id=request_id,
        prompt=model_prompt,
        params=common_pb2.InferenceParams(
            max_tokens=params.max_tokens,
            temperature=params.temperature,
            top_k=params.top_k,
            draft_tokens=params.draft_tokens,
        ),
        model_id=DRAFT_MODEL,
        timestamp=int(time.time() * 1000),
    )


def _final_response_to_summary(final_response):
    final_token_events = [
        TokenEvent(
            text=t.text,
            type="accepted",
            token_id=t.token_id,
            logprob=t.logprob,
        )
        for t in final_response.tokens
    ]
    generated_text = "".join(t.text for t in final_token_events)

    return InferenceResponse(
        request_id=final_response.request_id,
        generated_text=generated_text,
        tokens=final_token_events,
        total_tokens=final_response.total_tokens,
        draft_tokens_generated=final_response.draft_tokens_generated,
        draft_tokens_accepted=final_response.draft_tokens_accepted,
        generation_time_ms=final_response.generation_time_ms,
        acceptance_rate=final_response.acceptance_rate,
        speculation_rounds=final_response.speculation_rounds,
    )


def _run_router_inference(prompt: str, params: InferenceRequest, request_id: str):
    import speculative_decoding_pb2_grpc

    def _decode_stream_token_type(encoded_logprob: float) -> tuple[str, float]:
        if encoded_logprob >= 1_500_000.0:
            return "corrected", 0.0
        if encoded_logprob >= 500_000.0:
            return "rejected", 0.0
        return "accepted", encoded_logprob

    request = _build_inference_job_request(prompt, params, request_id)

    response = httpx.post(
        f"{_router_base_url()}/route-request",
        json={
            "request_id": request.request_id,
            "prompt": request.prompt,
            "model_id": request.model_id,
            "priority": 0,
        },
        timeout=ROUTER_GRPC_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    route_response = response.json()

    if route_response.get("status") != "success":
        raise RuntimeError(route_response.get("message") or "router failed to assign a draft node")
    if not route_response.get("assigned_draft_node_address"):
        raise RuntimeError("router did not return an assigned draft node address")

    draft_channel = grpc.insecure_channel(route_response["assigned_draft_node_address"])
    try:
        draft_stub = speculative_decoding_pb2_grpc.DraftNodeServiceStub(draft_channel)
        final_response = None
        synthetic_round = 0
        emitted_output_tokens = 0
        for chunk in draft_stub.StreamInference(
            request,
            timeout=DRAFT_NODE_GRPC_TIMEOUT_SECONDS,
        ):
            if chunk.is_final:
                final_response = chunk.final_response
                break

            if not chunk.HasField("token"):
                continue

            synthetic_round += 1
            token_type, token_logprob = _decode_stream_token_type(chunk.token.logprob)
            token_event = TokenEvent(
                text=chunk.token.text,
                type=token_type,
                token_id=chunk.token.token_id,
                logprob=token_logprob,
            )
            if token_type in ("accepted", "corrected"):
                emitted_output_tokens += 1
            if token_type == "accepted":
                round_event = RoundEvent(
                    round_num=synthetic_round,
                    drafted=1,
                    accepted=1,
                    corrected=0,
                    verification_time_ms=0.0,
                    acceptance_rate=1.0,
                )
            elif token_type == "rejected":
                round_event = RoundEvent(
                    round_num=synthetic_round,
                    drafted=1,
                    accepted=0,
                    corrected=0,
                    verification_time_ms=0.0,
                    acceptance_rate=0.0,
                )
            else:
                round_event = RoundEvent(
                    round_num=synthetic_round,
                    drafted=1,
                    accepted=0,
                    corrected=1,
                    verification_time_ms=0.0,
                    acceptance_rate=0.0,
                )
            yield (
                "round",
                round_event,
                [token_event],
            )
    finally:
        draft_channel.close()

    if final_response is None:
        raise RuntimeError("draft node did not return a final response")

    # Reconcile any trailing output tokens that may be present in final response
    # but were not emitted via stream chunks.
    if emitted_output_tokens < len(final_response.tokens):
        for token in final_response.tokens[emitted_output_tokens:]:
            synthetic_round += 1
            token_event = TokenEvent(
                text=token.text,
                type="accepted",
                token_id=token.token_id,
                logprob=token.logprob,
            )
            yield (
                "round",
                RoundEvent(
                    round_num=synthetic_round,
                    drafted=1,
                    accepted=1,
                    corrected=0,
                    verification_time_ms=0.0,
                    acceptance_rate=1.0,
                ),
                [token_event],
            )

    yield ("done", _final_response_to_summary(final_response), [])


def run_real_inference(prompt: str, params: InferenceRequest):
    """
    Run speculative decoding through router-assigned draft node.
    Yields (event_type, data, tokens) tuples.
    """
    request_id = str(uuid.uuid4())[:8]
    if not ROUTER_ADDRESS:
        raise RuntimeError("ROUTER_ADDRESS must be set when MOCK_MODE is disabled")
    yield from _run_router_inference(prompt, params, request_id)

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

        token_buffer: list[TokenEvent] = []

        async def flush_tokens():
            nonlocal token_buffer
            if not token_buffer:
                return
            for token in token_buffer:
                await websocket.send_text(json.dumps({
                    "type": "token",
                    "data": token.model_dump(),
                }))
            token_buffer = []

        gen = run_inference(params.prompt, params)
        while True:
            next_item = await asyncio.to_thread(lambda: next(gen, None))
            if next_item is None:
                break

            event_type, data, tokens = next_item
            if event_type == "round":
                for token in tokens:
                    token_buffer.append(token)
                    if len(token_buffer) >= TOKEN_SEND_BATCH_SIZE:
                        await flush_tokens()
                await flush_tokens()
                await websocket.send_text(json.dumps({
                    "type": "round",
                    "data": data.model_dump(),
                }))
            elif event_type == "done":
                await flush_tokens()
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
    return {
        "status": "ok",
        "mock": MOCK_MODE,
        "router_enabled": bool(ROUTER_ADDRESS),
        "router_address": ROUTER_ADDRESS or None,
    }


@app.post("/api/warmup")
async def warmup():
    """
    Warm up draft model/client so first prompt has low latency.
    Triggered by frontend on page load.
    """
    if MOCK_MODE:
        return {"status": "ok", "mock": True, "warmed": False}
    if not ROUTER_ADDRESS:
        return {"status": "error", "mock": False, "message": "ROUTER_ADDRESS is not configured"}
    try:
        response = await asyncio.to_thread(
            lambda: httpx.get(
                f"{_router_base_url()}/health",
                timeout=ROUTER_GRPC_TIMEOUT_SECONDS,
            )
        )
        response.raise_for_status()
    except Exception as exc:
        return {"status": "error", "mock": False, "router_enabled": True, "message": str(exc)}

    return {"status": "ok", "mock": False, "warmed": False, "router_enabled": True}

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
    print(f"  Mode: {'MOCK (no GPU)' if MOCK_MODE else 'LIVE (router + draft nodes)'}")
    if not MOCK_MODE:
        print(f"  Draft model: {DRAFT_MODEL}")
        print(f"  Router mode: {'enabled' if ROUTER_ADDRESS else 'disabled (REQUIRED)'}")
        print(f"  Router address: {ROUTER_ADDRESS or '<unset>'}")
        print(f"  Prompt format: {PROMPT_FORMAT}")
        print(f"  System prompt enabled: {'yes' if SYSTEM_PROMPT.strip() else 'no'}")
    print(f"{'='*60}\n")

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=args.port)
