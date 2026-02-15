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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ── Configuration ──

DRAFT_MODEL = os.getenv("DRAFT_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
MODAL_APP_NAME = os.getenv("MODAL_APP_NAME", "treehacks-verification-service")
MODAL_CLASS_NAME = os.getenv("MODAL_CLASS_NAME", "VerificationService")
BRIDGE_PORT = int(os.getenv("BRIDGE_PORT", "8000"))
MOCK_MODE = os.getenv("MOCK_MODE", "").lower() in ("1", "true", "yes")
TOKEN_SEND_BATCH_SIZE = max(1, int(os.getenv("TOKEN_SEND_BATCH_SIZE", "1")))
DEFAULT_MAX_TOKENS = int(os.getenv("DEFAULT_MAX_TOKENS", "512"))
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "You are a helpful AI assistant.")
PROMPT_FORMAT = os.getenv("PROMPT_FORMAT", "chatml").lower()

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

# ── Real inference (delegated to DraftNodeClient + Modal target) ──

def _get_draft_client():
    if not hasattr(_get_draft_client, "_client"):
        from workers.draft_node.client import DraftNodeClient
        _get_draft_client._client = DraftNodeClient(
            draft_model=DRAFT_MODEL,
            num_draft_tokens=5,
            modal_app_name=MODAL_APP_NAME,
            modal_class_name=MODAL_CLASS_NAME,
        )
    return _get_draft_client._client


def run_real_inference(prompt: str, params: InferenceRequest):
    """
    Run speculative decoding through DraftNodeClient.
    Yields (event_type, data, tokens) tuples.
    """
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "proto"))
    import common_pb2
    import speculative_decoding_pb2

    request_id = str(uuid.uuid4())[:8]
    model_prompt = _build_model_prompt(prompt)

    request = speculative_decoding_pb2.InferenceJobRequest(
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

    client = _get_draft_client()
    final_response = None

    for event_type, data, tokens in client.execute_inference_stream(request):
        if event_type == "round":
            round_event = RoundEvent(**data)
            token_events = [
                TokenEvent(
                    text=t["text"],
                    type=t["type"],
                    token_id=t.get("token_id", 0),
                    logprob=t.get("logprob", 0.0),
                )
                for t in tokens
            ]
            yield ("round", round_event, token_events)
        elif event_type == "done":
            final_response = data

    if final_response is None:
        raise RuntimeError("DraftNodeClient did not produce a final inference response")

    final_token_events = [
        TokenEvent(
            text=t.text,
            type="accepted",
            token_id=t.token_id,
            logprob=t.logprob,
        )
        for t in final_response.tokens
    ]

    summary = InferenceResponse(
        request_id=final_response.request_id,
        generated_text=final_response.generated_text,
        tokens=final_token_events,
        total_tokens=final_response.total_tokens,
        draft_tokens_generated=final_response.draft_tokens_generated,
        draft_tokens_accepted=final_response.draft_tokens_accepted,
        generation_time_ms=final_response.generation_time_ms,
        acceptance_rate=final_response.acceptance_rate,
        speculation_rounds=final_response.speculation_rounds,
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


@app.post("/api/warmup")
async def warmup():
    """
    Warm up draft model/client so first prompt has low latency.
    Triggered by frontend on page load.
    """
    if MOCK_MODE:
        return {"status": "ok", "mock": True, "warmed": False}

    await asyncio.to_thread(_get_draft_client)
    return {"status": "ok", "mock": False, "warmed": True}

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
    print(f"  Mode: {'MOCK (no GPU)' if MOCK_MODE else 'LIVE (vLLM + Modal)'}")
    if not MOCK_MODE:
        print(f"  Modal app: {MODAL_APP_NAME}")
        print(f"  Modal class: {MODAL_CLASS_NAME}")
        print(f"  Draft model: {DRAFT_MODEL}")
        print(f"  Prompt format: {PROMPT_FORMAT}")
        print(f"  System prompt enabled: {'yes' if SYSTEM_PROMPT.strip() else 'no'}")
    print(f"{'='*60}\n")

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=args.port)
