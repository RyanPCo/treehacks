#!/bin/bash
# Start the FastAPI frontend bridge server
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f "$HOME/.venv-vllm-metal/bin/activate" ]; then
  source "$HOME/.venv-vllm-metal/bin/activate"
elif [ -f ".venv/bin/activate" ]; then
  source ".venv/bin/activate"
fi

export DRAFT_MODEL="${DRAFT_MODEL:-rd211/Qwen3-0.6B-Instruct}"
export BRIDGE_PORT="${BRIDGE_PORT:-8000}"
export ROUTER_ADDRESS="${ROUTER_ADDRESS:-127.0.0.1:50061}"
export DEFAULT_MAX_TOKENS="${DEFAULT_MAX_TOKENS:-512}"
export SYSTEM_PROMPT="${SYSTEM_PROMPT:-You are a precise, helpful assistant. Follow the user instructions exactly. If the request is ambiguous, ask one brief clarifying question before proceeding. Be concise by default. For coding tasks, provide correct, runnable solutions and call out assumptions. Do not invent facts; when uncertain, say so clearly.}"

export PROMPT_FORMAT="${PROMPT_FORMAT:-chatml}"

echo "Starting Frontend Bridge..."
echo "  Draft model: $DRAFT_MODEL"
echo "  Router address: ${ROUTER_ADDRESS:-<disabled>}"
echo "  Prompt format: $PROMPT_FORMAT"
echo "  System prompt: $SYSTEM_PROMPT"
echo "  Bridge port: $BRIDGE_PORT"

python workers/frontend_bridge/server.py --port "$BRIDGE_PORT"
