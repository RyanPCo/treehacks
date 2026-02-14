#!/bin/bash
# Start the target model server

cd "$(dirname "$0")/target_node"
source /home/dgorb/Github/treehacks/.venv/bin/activate

echo "Starting target model server on port 50051..."
python server.py
