// Shared types mirroring the FastAPI bridge Pydantic models

export interface InferenceRequest {
  prompt: string
  max_tokens?: number
  temperature?: number
  top_k?: number
  draft_tokens?: number
}

export interface TokenEvent {
  text: string
  type: "accepted" | "rejected" | "corrected"
  token_id?: number
  logprob?: number
}

export interface RoundEvent {
  round_num: number
  drafted: number
  accepted: number
  corrected: number
  verification_time_ms: number
  acceptance_rate: number
}

export interface InferenceResponse {
  request_id: string
  generated_text: string
  tokens: TokenEvent[]
  total_tokens: number
  draft_tokens_generated: number
  draft_tokens_accepted: number
  generation_time_ms: number
  acceptance_rate: number
  speculation_rounds: number
}

export interface NodeInfo {
  id: string
  type: "draft" | "target"
  hardware: string
  model: string
  status: "online" | "offline" | "busy"
  latency: number
  price: number
  gpu_memory: string
}

export interface NetworkStats {
  active_draft_nodes: number
  active_target_nodes: number
  total_tps: number
  avg_acceptance_rate: number
  avg_cost_per_1k: number
}

/** WebSocket message from the bridge */
export type StreamMessage =
  | { type: "token"; data: TokenEvent }
  | { type: "round"; data: RoundEvent }
  | { type: "done"; data: InferenceResponse }
  | { type: "error"; data: { message: string } }
