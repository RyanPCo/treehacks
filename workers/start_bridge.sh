#!/bin/bash
# Start the FastAPI frontend bridge server
cd "$(dirname "$0")/.."

export VERIFICATION_SERVER="${VERIFICATION_SERVER:-localhost:50051}"
export DRAFT_MODEL="${DRAFT_MODEL:-Qwen/Qwen2.5-1.5B-Instruct}"
export BRIDGE_PORT="${BRIDGE_PORT:-8000}"

echo "Starting Frontend Bridge..."
echo "  Verification server: $VERIFICATION_SERVER"
echo "  Draft model: $DRAFT_MODEL"
echo "  Bridge port: $BRIDGE_PORT"

python -m uvicorn workers.frontend_bridge.server:app --host 0.0.0.0 --port "$BRIDGE_PORT" --reload
