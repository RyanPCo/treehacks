import type {
  InferenceRequest,
  InferenceResponse,
  StreamMessage,
  NodeInfo,
  NetworkStats,
} from "./types"

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
const WS_URL = API_URL.replace(/^http/, "ws")

/** POST /api/inference — full (non-streaming) inference */
export async function submitInference(
  req: InferenceRequest,
): Promise<InferenceResponse> {
  const res = await fetch(`${API_URL}/api/inference`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  })
  if (!res.ok) throw new Error(`Inference failed: ${res.statusText}`)
  return res.json()
}

/**
 * WebSocket streaming inference.
 * Returns a cleanup function to close the socket.
 */
export function streamInference(
  req: InferenceRequest,
  onMessage: (msg: StreamMessage) => void,
  onError?: (err: Event | Error) => void,
  onClose?: () => void,
): () => void {
  const ws = new WebSocket(`${WS_URL}/api/inference/stream`)

  ws.onopen = () => {
    ws.send(JSON.stringify(req))
  }

  ws.onmessage = (event) => {
    try {
      const msg: StreamMessage = JSON.parse(event.data)
      onMessage(msg)
    } catch (e) {
      onError?.(e instanceof Error ? e : new Error(String(e)))
    }
  }

  ws.onerror = (event) => {
    onError?.(event)
  }

  ws.onclose = () => {
    onClose?.()
  }

  return () => {
    ws.close()
  }
}

/** GET /api/nodes */
export async function fetchNodes(): Promise<NodeInfo[]> {
  const res = await fetch(`${API_URL}/api/nodes`)
  if (!res.ok) throw new Error(`Failed to fetch nodes: ${res.statusText}`)
  return res.json()
}

/** GET /api/stats */
export async function fetchStats(): Promise<NetworkStats> {
  const res = await fetch(`${API_URL}/api/stats`)
  if (!res.ok) throw new Error(`Failed to fetch stats: ${res.statusText}`)
  return res.json()
}

/** GET /api/health */
export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_URL}/api/health`)
    return res.ok
  } catch {
    return false
  }
}
