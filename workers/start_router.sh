#!/bin/bash
# Start the router service
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f "$HOME/.venv-vllm-metal/bin/activate" ]; then
  source "$HOME/.venv-vllm-metal/bin/activate"
elif [ -f ".venv/bin/activate" ]; then
  source ".venv/bin/activate"
fi

export ROUTER_HOST="${ROUTER_HOST:-0.0.0.0}"
export ROUTER_PORT="${ROUTER_PORT:-50061}"
export ROUTER_HEARTBEAT_TIMEOUT_SECONDS="${ROUTER_HEARTBEAT_TIMEOUT_SECONDS:-30}"

echo "Starting Router Service..."
echo "  Listen: ${ROUTER_HOST}:${ROUTER_PORT}"
echo "  Heartbeat timeout: ${ROUTER_HEARTBEAT_TIMEOUT_SECONDS}s"

python router/server.py \
  --host "${ROUTER_HOST}" \
  --port "${ROUTER_PORT}" \
  --heartbeat-timeout "${ROUTER_HEARTBEAT_TIMEOUT_SECONDS}"
