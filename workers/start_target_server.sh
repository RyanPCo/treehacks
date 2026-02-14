#!/bin/bash
# Start the target model server
#
# Usage:
#   ./start_target_server.sh                          # Use deterministic (default)
#   ./start_target_server.sh --strategy probabilistic # Use probabilistic
#   ./start_target_server.sh --strategy threshold --threshold 0.2 # Use threshold with custom value
#   ./start_target_server.sh --verbose                # Enable verbose logging

cd "$(dirname "$0")/target_node"
source /home/ryan/Code/treehacks/.venv/bin/activate

echo "Starting target model server..."
python server.py "$@"
