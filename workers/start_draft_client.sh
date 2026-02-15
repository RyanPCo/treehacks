#!/bin/bash
# Start the draft node gRPC server
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f "$HOME/.venv-vllm-metal/bin/activate" ]; then
  source "$HOME/.venv-vllm-metal/bin/activate"
elif [ -f ".venv/bin/activate" ]; then
  source ".venv/bin/activate"
fi

export DRAFT_NODE_PORT="${DRAFT_NODE_PORT:-50071}"
export ROUTER_ADDRESS="${ROUTER_ADDRESS:-localhost:50061}"
export DRAFT_NODE_ADVERTISE_ADDRESS="${DRAFT_NODE_ADVERTISE_ADDRESS:-127.0.0.1:${DRAFT_NODE_PORT}}"
export DRAFT_MODEL="${DRAFT_MODEL:-Qwen/Qwen2.5-0.5B-Instruct}"
export MODAL_APP_NAME="${MODAL_APP_NAME:-treehacks-verification-service}"
export MODAL_CLASS_NAME="${MODAL_CLASS_NAME:-VerificationService}"

echo "Starting Draft Node Service..."
echo "  Listen: 0.0.0.0:${DRAFT_NODE_PORT}"
echo "  Advertise: ${DRAFT_NODE_ADVERTISE_ADDRESS}"
echo "  Router: ${ROUTER_ADDRESS}"
echo "  Draft model: ${DRAFT_MODEL}"

python workers/draft_node/client.py \
  --port "${DRAFT_NODE_PORT}" \
  --advertise-address "${DRAFT_NODE_ADVERTISE_ADDRESS}" \
  --router-address "${ROUTER_ADDRESS}" \
  --draft-model "${DRAFT_MODEL}" \
  --modal-app-name "${MODAL_APP_NAME}" \
  --modal-class-name "${MODAL_CLASS_NAME}"
