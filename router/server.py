"""HTTP router service connecting frontend bridge requests to draft nodes."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import threading
import time
import uuid

from fastapi import FastAPI
from pydantic import BaseModel, Field
import uvicorn


DEFAULT_HEARTBEAT_INTERVAL_MS = 5000
DEFAULT_HEARTBEAT_TIMEOUT_S = 30


class ModelInfo(BaseModel):
    model_id: str = ""
    model_name: str = ""
    version: str = ""


class ResourceStats(BaseModel):
    gpu_utilization: float = 0.0
    memory_used_bytes: int = 0
    memory_total_bytes: int = 0
    active_requests: int = 0
    tokens_per_second: float = 0.0


class WorkerRegistration(BaseModel):
    worker_id: str = ""
    address: str
    worker_type: str = "target"
    model_info: ModelInfo = Field(default_factory=ModelInfo)
    gpu_model: str = ""
    gpu_memory_bytes: int = 0
    gpu_count: int = 0
    max_concurrent_requests: int = 1
    max_batch_size: int = 1


class WorkerRegistrationResponse(BaseModel):
    accepted: bool
    message: str
    assigned_worker_id: str = ""


class WorkerHeartbeatRequest(BaseModel):
    worker_id: str
    stats: ResourceStats = Field(default_factory=ResourceStats)


class WorkerHeartbeatResponse(BaseModel):
    acknowledged: bool
    next_heartbeat_interval_ms: int


class DraftNodeRegistration(BaseModel):
    draft_node_id: str = ""
    address: str
    model_info: ModelInfo = Field(default_factory=ModelInfo)
    gpu_model: str = ""
    gpu_memory_bytes: int = 0
    max_draft_tokens: int = 5


class DraftNodeRegistrationResponse(BaseModel):
    accepted: bool
    message: str
    assigned_node_id: str = ""


class DraftNodeHeartbeatRequest(BaseModel):
    draft_node_id: str
    stats: ResourceStats = Field(default_factory=ResourceStats)
    available_capacity: int = 1


class DraftNodeHeartbeatResponse(BaseModel):
    acknowledged: bool
    next_heartbeat_interval_ms: int


class RouteRequestMessage(BaseModel):
    request_id: str
    prompt: str
    model_id: str = ""
    priority: int = 0


class RouteRequestResponse(BaseModel):
    request_id: str
    assigned_draft_node_id: str = ""
    assigned_draft_node_address: str = ""
    status: str
    message: str
    estimated_queue_time_ms: int = 0


class WorkerAssignmentRequest(BaseModel):
    request_id: str
    draft_node_id: str = ""
    model_id: str = ""


class WorkerAssignmentResponse(BaseModel):
    request_id: str
    worker_id: str = ""
    worker_address: str = ""
    model_info: ModelInfo = Field(default_factory=ModelInfo)
    status: str
    message: str


@dataclass
class DraftNodeRecord:
    draft_node_id: str
    address: str
    model_info: ModelInfo
    gpu_model: str
    gpu_memory_bytes: int
    max_draft_tokens: int
    available_capacity: int = 1
    stats: ResourceStats = field(default_factory=ResourceStats)
    last_heartbeat_s: float = field(default_factory=time.time)


@dataclass
class WorkerRecord:
    worker_id: str
    address: str
    worker_type: str
    model_info: ModelInfo
    gpu_model: str
    gpu_memory_bytes: int
    gpu_count: int
    max_concurrent_requests: int
    max_batch_size: int
    stats: ResourceStats = field(default_factory=ResourceStats)
    last_heartbeat_s: float = field(default_factory=time.time)


class RouterState:
    """Thread-safe in-memory registry and routing state."""

    def __init__(self, heartbeat_timeout_s: int = DEFAULT_HEARTBEAT_TIMEOUT_S):
        self.heartbeat_timeout_s = heartbeat_timeout_s
        self._draft_nodes: dict[str, DraftNodeRecord] = {}
        self._workers: dict[str, WorkerRecord] = {}
        self._draft_rr_cursor: dict[str, int] = {}
        self._worker_rr_cursor: dict[str, int] = {}
        self._lock = threading.Lock()

    def _is_active(self, last_heartbeat_s: float) -> bool:
        return (time.time() - last_heartbeat_s) <= self.heartbeat_timeout_s

    def _purge_stale_locked(self) -> None:
        stale_drafts = [
            node_id
            for node_id, record in self._draft_nodes.items()
            if not self._is_active(record.last_heartbeat_s)
        ]
        for node_id in stale_drafts:
            del self._draft_nodes[node_id]

        stale_workers = [
            worker_id
            for worker_id, record in self._workers.items()
            if not self._is_active(record.last_heartbeat_s)
        ]
        for worker_id in stale_workers:
            del self._workers[worker_id]

    def register_draft_node(self, request: DraftNodeRegistration) -> str:
        assigned_id = request.draft_node_id.strip() or f"draft-{uuid.uuid4().hex[:8]}"
        with self._lock:
            self._draft_nodes[assigned_id] = DraftNodeRecord(
                draft_node_id=assigned_id,
                address=request.address,
                model_info=request.model_info,
                gpu_model=request.gpu_model,
                gpu_memory_bytes=request.gpu_memory_bytes,
                max_draft_tokens=request.max_draft_tokens,
            )
        return assigned_id

    def draft_heartbeat(self, request: DraftNodeHeartbeatRequest) -> bool:
        with self._lock:
            record = self._draft_nodes.get(request.draft_node_id)
            if record is None:
                return False
            record.stats = request.stats
            record.available_capacity = request.available_capacity
            record.last_heartbeat_s = time.time()
            return True

    def register_worker(self, request: WorkerRegistration) -> str:
        assigned_id = request.worker_id.strip() or f"worker-{uuid.uuid4().hex[:8]}"
        with self._lock:
            self._workers[assigned_id] = WorkerRecord(
                worker_id=assigned_id,
                address=request.address,
                worker_type=request.worker_type,
                model_info=request.model_info,
                gpu_model=request.gpu_model,
                gpu_memory_bytes=request.gpu_memory_bytes,
                gpu_count=request.gpu_count,
                max_concurrent_requests=request.max_concurrent_requests,
                max_batch_size=request.max_batch_size,
            )
        return assigned_id

    def worker_heartbeat(self, request: WorkerHeartbeatRequest) -> bool:
        with self._lock:
            record = self._workers.get(request.worker_id)
            if record is None:
                return False
            record.stats = request.stats
            record.last_heartbeat_s = time.time()
            return True

    def select_draft_node(self, model_id: str) -> DraftNodeRecord | None:
        with self._lock:
            self._purge_stale_locked()
            candidates = [
                record
                for record in self._draft_nodes.values()
                if record.available_capacity != 0
            ]
            if not candidates:
                return None

            if model_id:
                matching = [
                    record
                    for record in candidates
                    if record.model_info.model_id == model_id
                    or record.model_info.model_name == model_id
                ]
                if matching:
                    candidates = matching

            candidates = sorted(candidates, key=lambda record: record.draft_node_id)
            key = model_id or "__all__"
            cursor = self._draft_rr_cursor.get(key, 0)
            selected = candidates[cursor % len(candidates)]
            self._draft_rr_cursor[key] = cursor + 1
            return selected

    def select_target_worker(self, model_id: str) -> WorkerRecord | None:
        with self._lock:
            self._purge_stale_locked()
            candidates = [
                record
                for record in self._workers.values()
                if record.worker_type == "target"
            ]
            if not candidates:
                return None

            if model_id:
                matching = [
                    record
                    for record in candidates
                    if record.model_info.model_id == model_id
                    or record.model_info.model_name == model_id
                ]
                if matching:
                    candidates = matching

            candidates = sorted(candidates, key=lambda record: record.worker_id)
            key = model_id or "__all__"
            cursor = self._worker_rr_cursor.get(key, 0)
            selected = candidates[cursor % len(candidates)]
            self._worker_rr_cursor[key] = cursor + 1
            return selected


STATE = RouterState()
app = FastAPI(title="SpecNet Router Service")


@app.post("/register-worker", response_model=WorkerRegistrationResponse)
def register_worker(request: WorkerRegistration):
    assigned_id = STATE.register_worker(request)
    print(f"Registered worker {assigned_id} at {request.address}")
    return WorkerRegistrationResponse(
        accepted=True,
        message="worker registered",
        assigned_worker_id=assigned_id,
    )


@app.post("/worker-heartbeat", response_model=WorkerHeartbeatResponse)
def worker_heartbeat(request: WorkerHeartbeatRequest):
    acknowledged = STATE.worker_heartbeat(request)
    return WorkerHeartbeatResponse(
        acknowledged=acknowledged,
        next_heartbeat_interval_ms=DEFAULT_HEARTBEAT_INTERVAL_MS,
    )


@app.post("/register-draft-node", response_model=DraftNodeRegistrationResponse)
def register_draft_node(request: DraftNodeRegistration):
    assigned_id = STATE.register_draft_node(request)
    print(
        f"Registered draft node {assigned_id} at {request.address} "
        f"(model={request.model_info.model_id or request.model_info.model_name})"
    )
    return DraftNodeRegistrationResponse(
        accepted=True,
        message="draft node registered",
        assigned_node_id=assigned_id,
    )


@app.post("/draft-heartbeat", response_model=DraftNodeHeartbeatResponse)
def draft_heartbeat(request: DraftNodeHeartbeatRequest):
    acknowledged = STATE.draft_heartbeat(request)
    return DraftNodeHeartbeatResponse(
        acknowledged=acknowledged,
        next_heartbeat_interval_ms=DEFAULT_HEARTBEAT_INTERVAL_MS,
    )


@app.post("/route-request", response_model=RouteRequestResponse)
def route_request(request: RouteRequestMessage):
    selected = STATE.select_draft_node(request.model_id)
    if selected is None:
        return RouteRequestResponse(
            request_id=request.request_id,
            status="resource_exhausted",
            message="no active draft nodes available",
            estimated_queue_time_ms=0,
        )

    return RouteRequestResponse(
        request_id=request.request_id,
        assigned_draft_node_id=selected.draft_node_id,
        assigned_draft_node_address=selected.address,
        status="success",
        message="request routed",
        estimated_queue_time_ms=0,
    )


@app.post("/worker-assignment", response_model=WorkerAssignmentResponse)
def worker_assignment(request: WorkerAssignmentRequest):
    selected = STATE.select_target_worker(request.model_id)
    if selected is None:
        return WorkerAssignmentResponse(
            request_id=request.request_id,
            status="resource_exhausted",
            message="no active target workers available",
        )

    return WorkerAssignmentResponse(
        request_id=request.request_id,
        worker_id=selected.worker_id,
        worker_address=selected.address,
        model_info=selected.model_info,
        status="success",
        message="worker assigned",
    )


@app.get("/health")
def health():
    return {
        "status": "ok",
        "draft_nodes": len(STATE._draft_nodes),
        "workers": len(STATE._workers),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="SpecNet Router Service")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=50061)
    parser.add_argument(
        "--heartbeat-timeout",
        type=int,
        default=DEFAULT_HEARTBEAT_TIMEOUT_S,
        help="Seconds after last heartbeat before a node is considered offline",
    )
    args = parser.parse_args()

    STATE.heartbeat_timeout_s = args.heartbeat_timeout

    print("\n" + "=" * 72)
    print("SpecNet Router Service")
    print(f"Address: {args.host}:{args.port}")
    print(f"Heartbeat timeout: {args.heartbeat_timeout}s")
    print("=" * 72 + "\n")

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
