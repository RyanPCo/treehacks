"use client"

import { useEffect, useState, useRef, useCallback } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { NetworkVisualizer, type NetworkPhase, type PacketEvent } from "@/components/network-visualizer"
import { ChatPanel, type VisibleToken } from "@/components/chat-panel"
import { ChatInput } from "@/components/chat-input"
import { LiveMetrics } from "@/components/live-metrics"
import { PanelRightOpen, PanelRightClose } from "lucide-react"
import { streamInference, checkHealth } from "@/lib/api"
import type { StreamMessage, TokenEvent } from "@/lib/types"

// ── Demo token data (fallback when backend is offline) ──
type TokenType = "accepted" | "rejected" | "corrected"
interface Token { text: string; type: TokenType }

const DEMO_TOKEN_STREAM: Token[] = [
  { text: "The", type: "accepted" },
  { text: " theory", type: "accepted" },
  { text: " of", type: "accepted" },
  { text: " relativity,", type: "accepted" },
  { text: " proposed", type: "accepted" },
  { text: " by", type: "accepted" },
  { text: " Albert", type: "accepted" },
  { text: " Einstein", type: "accepted" },
  { text: " in", type: "accepted" },
  { text: " the early", type: "rejected" },
  { text: " 1905", type: "corrected" },
  { text: " and", type: "accepted" },
  { text: " 1915,", type: "accepted" },
  { text: " fundamentally", type: "accepted" },
  { text: " changed", type: "rejected" },
  { text: " revolutionized", type: "corrected" },
  { text: " our", type: "accepted" },
  { text: " understanding", type: "accepted" },
  { text: " of", type: "accepted" },
  { text: " space", type: "accepted" },
  { text: " and", type: "accepted" },
  { text: " time.", type: "accepted" },
  { text: " Special", type: "accepted" },
  { text: " relativity", type: "accepted" },
  { text: " shows", type: "rejected" },
  { text: " demonstrates", type: "corrected" },
  { text: " that", type: "accepted" },
  { text: " the", type: "accepted" },
  { text: " speed", type: "accepted" },
  { text: " of", type: "accepted" },
  { text: " light", type: "accepted" },
  { text: " is", type: "accepted" },
  { text: " constant", type: "accepted" },
  { text: " for", type: "accepted" },
  { text: " all", type: "accepted" },
  { text: " observers,", type: "accepted" },
  { text: " leading", type: "accepted" },
  { text: " to", type: "accepted" },
  { text: " the", type: "accepted" },
  { text: " famous", type: "rejected" },
  { text: " iconic", type: "corrected" },
  { text: " equation", type: "accepted" },
  { text: " E=mc\u00B2.", type: "accepted" },
  { text: " General", type: "accepted" },
  { text: " relativity", type: "accepted" },
  { text: " extends", type: "accepted" },
  { text: " this", type: "accepted" },
  { text: " by", type: "accepted" },
  { text: " explaining", type: "rejected" },
  { text: " describing", type: "corrected" },
  { text: " gravity", type: "accepted" },
  { text: " not", type: "accepted" },
  { text: " as", type: "accepted" },
  { text: " a", type: "accepted" },
  { text: " force,", type: "accepted" },
  { text: " but", type: "accepted" },
  { text: " as", type: "accepted" },
  { text: " a", type: "accepted" },
  { text: " curvature", type: "accepted" },
  { text: " of", type: "accepted" },
  { text: " spacetime", type: "accepted" },
  { text: " caused", type: "accepted" },
  { text: " by", type: "accepted" },
  { text: " mass", type: "rejected" },
  { text: " massive objects.", type: "corrected" },
]

const DEMO_PROMPT = "Explain the theory of relativity."

// ── Animation helpers (for demo mode) ──
type AnimStep =
  | { kind: "accepted"; token: Token; index: number }
  | { kind: "rejection"; rejected: Token; corrected: Token; rejIdx: number; corrIdx: number }

function buildSteps(tokens: Token[]): AnimStep[] {
  const steps: AnimStep[] = []
  let i = 0
  while (i < tokens.length) {
    const t = tokens[i]
    if (t.type === "rejected" && i + 1 < tokens.length && tokens[i + 1].type === "corrected") {
      steps.push({ kind: "rejection", rejected: t, corrected: tokens[i + 1], rejIdx: i, corrIdx: i + 1 })
      i += 2
    } else {
      steps.push({ kind: "accepted", token: t, index: i })
      i += 1
    }
  }
  return steps
}

const DEMO_STEPS = buildSteps(DEMO_TOKEN_STREAM)
const ACCEPTED_DELAY = 60
const REJECTED_SHOW_DELAY = 80
const STRIKE_PAUSE = 500
const INITIAL_DELAY = 800

// Token animation delay for live streaming
const STREAM_TOKEN_DELAY = 20
const WORDS_PER_PACKET = 3
const ESTIMATED_CLOUD_COST_PER_1K_TOKENS_USD = 0.5
const ESTIMATED_TIME_SAVED_PER_ACCEPTED_TOKEN_MS = 12

function countWords(text: string): number {
  return text.trim().split(/\s+/).filter(Boolean).length
}

export function DashboardBody() {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)

  // Shared state
  const [phase, setPhase] = useState<NetworkPhase>("idle")
  const [prompt, setPrompt] = useState(DEMO_PROMPT)
  const [visibleTokens, setVisibleTokens] = useState<VisibleToken[]>([])
  const [done, setDone] = useState(false)
  const [counts, setCounts] = useState({ accepted: 0, rejected: 0, corrected: 0, drafted: 0 })
  const [packets, setPackets] = useState<PacketEvent[]>([])

  // Metrics from backend
  const [acceptanceRate, setAcceptanceRate] = useState(82)
  const [totalInferenceTimeSavedMs, setTotalInferenceTimeSavedMs] = useState(320)
  const [costSavingsDollars, setCostSavingsDollars] = useState(0.42)

  const packetId = useRef(0)
  const packetWordBuffer = useRef<{ draft: number; verify: number }>({ draft: 0, verify: 0 })
  const streamStartMs = useRef(0)
  const generatedOutputTokens = useRef(0)
  const acceptedDraftTokens = useRef(0)
  const stepIdx = useRef(0)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const cleanupRef = useRef<(() => void) | null>(null)

  // Check backend health on mount
  useEffect(() => {
    checkHealth().then(setBackendOnline)
  }, [])

  const emitPacket = useCallback((lane: "draft" | "verify", color: string) => {
    const id = packetId.current++
    const direction = lane === "draft" ? "ltr" as const : "rtl" as const
    setPackets((prev) => [...prev, { id, direction, lane, color }])
  }, [])

  const emitPacketForWords = useCallback((lane: "draft" | "verify", color: string, text: string) => {
    const words = countWords(text)
    if (words === 0) return

    packetWordBuffer.current[lane] += words
    while (packetWordBuffer.current[lane] >= WORDS_PER_PACKET) {
      emitPacket(lane, color)
      packetWordBuffer.current[lane] -= WORDS_PER_PACKET
    }
  }, [emitPacket])

  const handlePacketDone = useCallback((id: number) => {
    setPackets((prev) => prev.filter((p) => p.id !== id))
  }, [])

  // ── Demo mode animation ──
  const processDemoStep = useCallback(() => {
    if (stepIdx.current >= DEMO_STEPS.length) {
      setDone(true)
      setPhase("complete")
      return
    }

    const step = DEMO_STEPS[stepIdx.current]
    stepIdx.current += 1

    if (step.kind === "accepted") {
      setPhase("drafting")
      emitPacketForWords("draft", "hsl(142, 71%, 45%)", step.token.text)
      emitPacketForWords("verify", "hsl(217, 91%, 60%)", step.token.text)
      setVisibleTokens(prev => [...prev, { text: step.token.text, type: step.token.type, phase: "settled" }])
      setCounts(prev => ({
        ...prev,
        drafted: prev.drafted + 1,
        accepted: step.token.type === "accepted" ? prev.accepted + 1 : prev.accepted,
        corrected: step.token.type === "corrected" ? prev.corrected + 1 : prev.corrected,
      }))
      timeoutRef.current = setTimeout(processDemoStep, ACCEPTED_DELAY)
    } else {
      setPhase("drafting")
      emitPacketForWords("draft", "hsl(142, 71%, 45%)", step.rejected.text)
      setVisibleTokens(prev => [...prev, { text: step.rejected.text, type: "rejected", phase: "appearing" }])
      setCounts(prev => ({ ...prev, drafted: prev.drafted + 1 }))

      timeoutRef.current = setTimeout(() => {
        setPhase("verifying")
        emitPacketForWords("verify", "hsl(48, 96%, 53%)", step.rejected.text)
        setVisibleTokens(prev => {
          const copy = [...prev]
          copy[copy.length - 1] = { ...copy[copy.length - 1], phase: "striking" }
          return copy
        })
        setCounts(prev => ({ ...prev, rejected: prev.rejected + 1 }))

        timeoutRef.current = setTimeout(() => {
          setVisibleTokens(prev => {
            const copy = [...prev]
            copy[copy.length - 1] = { ...copy[copy.length - 1], phase: "hidden" }
            return copy
          })

          timeoutRef.current = setTimeout(() => {
            setPhase("correcting")
            emitPacketForWords("draft", "hsl(217, 91%, 60%)", step.corrected.text)
            emitPacketForWords("verify", "hsl(217, 91%, 60%)", step.corrected.text)
            setVisibleTokens(prev => {
              const withoutHidden = prev.filter(t => t.phase !== "hidden")
              return [...withoutHidden, { text: step.corrected.text, type: "corrected", phase: "appearing" }]
            })
            setCounts(prev => ({ ...prev, drafted: prev.drafted + 1, corrected: prev.corrected + 1 }))

            timeoutRef.current = setTimeout(() => {
              setVisibleTokens(prev => {
                const copy = [...prev]
                copy[copy.length - 1] = { ...copy[copy.length - 1], phase: "settled" }
                return copy
              })
              setPhase("drafting")
              timeoutRef.current = setTimeout(processDemoStep, ACCEPTED_DELAY)
            }, 150)
          }, 100)
        }, STRIKE_PAUSE)
      }, REJECTED_SHOW_DELAY)
    }
  }, [emitPacketForWords])

  // ── Live streaming mode ──
  const handleSubmit = useCallback((userPrompt: string) => {
    // Reset state
    setPrompt(userPrompt)
    setVisibleTokens([])
    setDone(false)
    setCounts({ accepted: 0, rejected: 0, corrected: 0, drafted: 0 })
    setPhase("idle")
    setIsStreaming(true)
    setTotalInferenceTimeSavedMs(0)
    setCostSavingsDollars(0)
    packetWordBuffer.current = { draft: 0, verify: 0 }
    streamStartMs.current = Date.now()
    generatedOutputTokens.current = 0
    acceptedDraftTokens.current = 0

    if (timeoutRef.current) clearTimeout(timeoutRef.current)
    if (cleanupRef.current) cleanupRef.current()

    // Queue for animating tokens one at a time
    const tokenQueue: TokenEvent[] = []
    let processing = false

    function processTokenQueue() {
      if (tokenQueue.length === 0) {
        processing = false
        return
      }
      processing = true
      const token = tokenQueue.shift()!

      // Determine phase/animation based on type
      if (token.type === "accepted") {
        setPhase("drafting")
        emitPacketForWords("draft", "hsl(142, 71%, 45%)", token.text)
        emitPacketForWords("verify", "hsl(217, 91%, 60%)", token.text)
        setVisibleTokens(prev => [...prev, { text: token.text, type: "accepted", phase: "settled" }])
        setCounts(prev => ({ ...prev, drafted: prev.drafted + 1, accepted: prev.accepted + 1 }))
        setTimeout(processTokenQueue, STREAM_TOKEN_DELAY)
      } else if (token.type === "rejected") {
        setPhase("verifying")
        emitPacketForWords("draft", "hsl(142, 71%, 45%)", token.text)
        emitPacketForWords("verify", "hsl(48, 96%, 53%)", token.text)
        setVisibleTokens(prev => [...prev, { text: token.text, type: "rejected", phase: "appearing" }])
        setCounts(prev => ({ ...prev, drafted: prev.drafted + 1, rejected: prev.rejected + 1 }))

        // Animate strike-through then hide
        setTimeout(() => {
          setVisibleTokens(prev => {
            const copy = [...prev]
            const last = copy.findLastIndex(t => t.type === "rejected" && t.phase === "appearing")
            if (last >= 0) copy[last] = { ...copy[last], phase: "striking" }
            return copy
          })
          setTimeout(() => {
            setVisibleTokens(prev => {
              const copy = [...prev]
              const last = copy.findLastIndex(t => t.type === "rejected" && t.phase === "striking")
              if (last >= 0) copy[last] = { ...copy[last], phase: "hidden" }
              return copy
            })
            setTimeout(() => {
              setVisibleTokens(prev => prev.filter(t => t.phase !== "hidden"))
              processTokenQueue()
            }, 100)
          }, STRIKE_PAUSE)
        }, REJECTED_SHOW_DELAY)
      } else if (token.type === "corrected") {
        setPhase("correcting")
        emitPacketForWords("draft", "hsl(217, 91%, 60%)", token.text)
        emitPacketForWords("verify", "hsl(217, 91%, 60%)", token.text)
        setVisibleTokens(prev => [...prev, { text: token.text, type: "corrected", phase: "appearing" }])
        setCounts(prev => ({ ...prev, drafted: prev.drafted + 1, corrected: prev.corrected + 1 }))

        setTimeout(() => {
          setVisibleTokens(prev => {
            const copy = [...prev]
            copy[copy.length - 1] = { ...copy[copy.length - 1], phase: "settled" }
            return copy
          })
          setTimeout(processTokenQueue, STREAM_TOKEN_DELAY)
        }, 150)
      }
    }

    function updateLiveSavingsFromAcceptedTokens() {
      const liveSavedMs = acceptedDraftTokens.current * ESTIMATED_TIME_SAVED_PER_ACCEPTED_TOKEN_MS
      const liveSavingsDollars =
        (acceptedDraftTokens.current / 1000) * ESTIMATED_CLOUD_COST_PER_1K_TOKENS_USD
      setTotalInferenceTimeSavedMs(liveSavedMs)
      setCostSavingsDollars(liveSavingsDollars)
    }

    const cleanup = streamInference(
      { prompt: userPrompt, max_tokens: 64 },
      (msg: StreamMessage) => {
        if (msg.type === "token") {
          if (msg.data.type === "accepted") {
            acceptedDraftTokens.current += 1
            updateLiveSavingsFromAcceptedTokens()
          }

          if (msg.data.type === "accepted" || msg.data.type === "corrected") {
            generatedOutputTokens.current += 1
          }
          tokenQueue.push(msg.data)
          if (!processing) processTokenQueue()
        } else if (msg.type === "round") {
          // Update metrics with round data
          setAcceptanceRate(msg.data.acceptance_rate * 100)
        } else if (msg.type === "done") {
          // Final metrics
          const data = msg.data
          setAcceptanceRate(data.acceptance_rate * 100)
          acceptedDraftTokens.current = data.draft_tokens_accepted
          updateLiveSavingsFromAcceptedTokens()
          // Mark done after queue drains
          const checkDone = () => {
            if (tokenQueue.length === 0 && !processing) {
              setDone(true)
              setPhase("complete")
              setIsStreaming(false)
            } else {
              setTimeout(checkDone, 100)
            }
          }
          checkDone()
        } else if (msg.type === "error") {
          setDone(true)
          setPhase("idle")
          setIsStreaming(false)
        }
      },
      () => {
        setDone(true)
        setPhase("idle")
        setIsStreaming(false)
      },
      () => {
        setIsStreaming(false)
      },
    )

    cleanupRef.current = cleanup
  }, [emitPacketForWords])

  // Start demo on mount if backend is offline
  useEffect(() => {
    if (backendOnline === false) {
      packetWordBuffer.current = { draft: 0, verify: 0 }
      timeoutRef.current = setTimeout(processDemoStep, INITIAL_DELAY)
    }
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
    }
  }, [backendOnline, processDemoStep])

  // Cleanup WebSocket on unmount
  useEffect(() => {
    return () => {
      if (cleanupRef.current) cleanupRef.current()
    }
  }, [])

  return (
    <div className="flex flex-1 gap-0 overflow-hidden">
      {/* Main content area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Network visualizer strip */}
        <div className="shrink-0 border-b border-border/30 px-4 py-3">
          <NetworkVisualizer phase={phase} packets={packets} onPacketDone={handlePacketDone} />
        </div>

        {/* Connection status */}
        {backendOnline !== null && (
          <div className="flex items-center gap-2 border-b border-border/20 px-4 py-1.5">
            <span className={`inline-block h-1.5 w-1.5 rounded-full ${backendOnline ? "bg-green-500" : "bg-yellow-500"}`} />
            <span className="text-[10px] text-muted-foreground">
              {backendOnline ? "Connected to SpecNet backend" : "Demo mode — backend offline"}
            </span>
          </div>
        )}

        {/* Chat area */}
        <div className="flex flex-1 flex-col gap-3 overflow-hidden p-4">
          <ChatPanel prompt={prompt} tokens={visibleTokens} done={done} counts={counts} />
          <ChatInput
            onSubmit={handleSubmit}
            disabled={isStreaming || (!backendOnline && !done)}
          />
        </div>
      </div>

      {/* Sidebar toggle rail */}
      <div className="flex shrink-0 flex-col border-l border-border/30">
        <button
          type="button"
          onClick={() => setSidebarOpen(prev => !prev)}
          className="flex h-10 w-10 items-center justify-center text-muted-foreground transition-colors hover:bg-secondary/50 hover:text-foreground"
          aria-label={sidebarOpen ? "Close metrics sidebar" : "Open metrics sidebar"}
        >
          {sidebarOpen ? (
            <PanelRightClose className="h-4 w-4" />
          ) : (
            <PanelRightOpen className="h-4 w-4" />
          )}
        </button>
      </div>

      {/* Right sidebar: Metrics */}
      <AnimatePresence initial={false}>
        {sidebarOpen && (
          <motion.aside
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 320, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: "easeInOut" }}
            className="shrink-0 overflow-hidden border-l border-border/30"
          >
            <div className="flex h-full w-80 flex-col gap-3 overflow-y-auto p-4">
              <div className="flex items-center justify-between">
                <h3 className="font-heading text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Live Metrics
                </h3>
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-green-500" />
                </span>
              </div>
              <LiveMetrics
                acceptanceRate={acceptanceRate}
                totalInferenceTimeSavedMs={totalInferenceTimeSavedMs}
                costSavingsDollars={costSavingsDollars}
              />
            </div>
          </motion.aside>
        )}
      </AnimatePresence>
    </div>
  )
}
