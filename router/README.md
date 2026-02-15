SpecNet router service (HTTP/FastAPI).

Responsibilities:
- Track active draft nodes and workers via register + heartbeat.
- Assign an incoming frontend request to a draft node by model-aware round robin.
- Return the selected draft node ID and address back to the frontend bridge.

Run:

```bash
./workers/start_router.sh
```
