#!/bin/bash
# Start the draft model client with speculative decoding

cd "$(dirname "$0")/draft_node"
source /home/dgorb/Github/treehacks/.venv/bin/activate

echo "Starting draft model client..."
python client.py
