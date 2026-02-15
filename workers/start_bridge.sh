#!/bin/bash
# Start the FastAPI frontend bridge server
cd "$(dirname "$0")/.."

export MODAL_APP_NAME="${MODAL_APP_NAME:-treehacks-verification-service}"
export MODAL_CLASS_NAME="${MODAL_CLASS_NAME:-VerificationService}"
export DRAFT_MODEL="${DRAFT_MODEL:-rd211/Qwen3-0.6B-Instruct}"
export BRIDGE_PORT="${BRIDGE_PORT:-8000}"
export DEFAULT_MAX_TOKENS="${DEFAULT_MAX_TOKENS:-512}"
export SYSTEM_PROMPT="${SYSTEM_PROMPT: -You are a precise, helpful assistant. Follow the user instructions exactly. If the request is ambiguous, ask one brief clarifying question before proceeding. Be concise by default. For coding tasks, provide correct, runnable solutions and call out assumptions. Do not invent facts; when uncertain, say so clearly.}"

export PROMPT_FORMAT="${PROMPT_FORMAT:-chatml}"

echo "Starting Frontend Bridge..."
echo "  Modal app: $MODAL_APP_NAME"
echo "  Modal class: $MODAL_CLASS_NAME"
echo "  Draft model: $DRAFT_MODEL"
echo "  Prompt format: $PROMPT_FORMAT"
echo "  System prompt: $SYSTEM_PROMPT"
echo "  Bridge port: $BRIDGE_PORT"

python -m uvicorn workers.frontend_bridge.server:app --host 0.0.0.0 --port "$BRIDGE_PORT" --reload
