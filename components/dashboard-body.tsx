"use client"

import { useEffect, useState, useRef, useCallback } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { NetworkVisualizer, type NetworkPhase, type PacketEvent } from "@/components/network-visualizer"
import { ChatPanel, type VisibleToken } from "@/components/chat-panel"
import { ChatInput } from "@/components/chat-input"
import { LiveMetrics } from "@/components/live-metrics"
import { PanelRightOpen, PanelRightClose } from "lucide-react"
import { streamInference, warmupDraftModel } from "@/lib/api"
import type { StreamMessage, TokenEvent } from "@/lib/types"

const REJECTED_SHOW_DELAY = 80
const STRIKE_PAUSE = 500
const STREAM_TOKEN_DELAY = 20
const WORDS_PER_PACKET = 3
const ESTIMATED_CLOUD_COST_PER_1K_TOKENS_USD = 0.5
const ESTIMATED_TIME_SAVED_PER_ACCEPTED_TOKEN_MS = 12

function countWords(text: string): number {
  return text.trim().split(/\s+/).filter(Boolean).length
}

export function DashboardBody() {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [isStreaming, setIsStreaming] = useState(false)

  const [phase, setPhase] = useState<NetworkPhase>("idle")
  const [prompt, setPrompt] = useState("")
  const [visibleTokens, setVisibleTokens] = useState<VisibleToken[]>([])
  const [done, setDone] = useState(true)
  const [counts, setCounts] = useState({ accepted: 0, rejected: 0, corrected: 0, drafted: 0 })
  const [packets, setPackets] = useState<PacketEvent[]>([])

  const [acceptanceRate, setAcceptanceRate] = useState(82)
  const [totalInferenceTimeSavedMs, setTotalInferenceTimeSavedMs] = useState(0)
  const [costSavingsDollars, setCostSavingsDollars] = useState(0)

  const packetId = useRef(0)
  const packetWordBuffer = useRef<{ draft: number; verify: number }>({ draft: 0, verify: 0 })
  const acceptedDraftTokens = useRef(0)
  const cleanupRef = useRef<(() => void) | null>(null)

  const emitPacket = useCallback((lane: "draft" | "verify", color: string) => {
    const id = packetId.current++
    const direction = lane === "draft" ? ("ltr" as const) : ("rtl" as const)
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

  const handleSubmit = useCallback((userPrompt: string) => {
    setPrompt(userPrompt)
    setVisibleTokens([])
    setDone(false)
    setCounts({ accepted: 0, rejected: 0, corrected: 0, drafted: 0 })
    setPhase("idle")
    setIsStreaming(true)
    setTotalInferenceTimeSavedMs(0)
    setCostSavingsDollars(0)

    packetWordBuffer.current = { draft: 0, verify: 0 }
    acceptedDraftTokens.current = 0

    if (cleanupRef.current) cleanupRef.current()

    const tokenQueue: TokenEvent[] = []
    let processing = false

    function processTokenQueue() {
      if (tokenQueue.length === 0) {
        processing = false
        return
      }
      processing = true
      const token = tokenQueue.shift()!

      if (token.type === "accepted") {
        setPhase("drafting")
        emitPacketForWords("draft", "hsl(142, 71%, 45%)", token.text)
        emitPacketForWords("verify", "hsl(217, 91%, 60%)", token.text)
        setVisibleTokens((prev) => [...prev, { text: token.text, type: "accepted", phase: "settled" }])
        setCounts((prev) => ({ ...prev, drafted: prev.drafted + 1, accepted: prev.accepted + 1 }))
        setTimeout(processTokenQueue, STREAM_TOKEN_DELAY)
      } else if (token.type === "rejected") {
        setPhase("verifying")
        emitPacketForWords("draft", "hsl(142, 71%, 45%)", token.text)
        emitPacketForWords("verify", "hsl(48, 96%, 53%)", token.text)
        setVisibleTokens((prev) => [...prev, { text: token.text, type: "rejected", phase: "appearing" }])
        setCounts((prev) => ({ ...prev, drafted: prev.drafted + 1, rejected: prev.rejected + 1 }))

        setTimeout(() => {
          setVisibleTokens((prev) => {
            const copy = [...prev]
            const last = copy.findLastIndex((t) => t.type === "rejected" && t.phase === "appearing")
            if (last >= 0) copy[last] = { ...copy[last], phase: "striking" }
            return copy
          })
          setTimeout(() => {
            setVisibleTokens((prev) => {
              const copy = [...prev]
              const last = copy.findLastIndex((t) => t.type === "rejected" && t.phase === "striking")
              if (last >= 0) copy[last] = { ...copy[last], phase: "hidden" }
              return copy
            })
            setTimeout(() => {
              setVisibleTokens((prev) => prev.filter((t) => t.phase !== "hidden"))
              processTokenQueue()
            }, 100)
          }, STRIKE_PAUSE)
        }, REJECTED_SHOW_DELAY)
      } else if (token.type === "corrected") {
        setPhase("correcting")
        emitPacketForWords("draft", "hsl(217, 91%, 60%)", token.text)
        emitPacketForWords("verify", "hsl(217, 91%, 60%)", token.text)
        setVisibleTokens((prev) => [...prev, { text: token.text, type: "corrected", phase: "appearing" }])
        setCounts((prev) => ({ ...prev, drafted: prev.drafted + 1, corrected: prev.corrected + 1 }))

        setTimeout(() => {
          setVisibleTokens((prev) => {
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
          tokenQueue.push(msg.data)
          if (!processing) processTokenQueue()
        } else if (msg.type === "round") {
          setAcceptanceRate(msg.data.acceptance_rate * 100)
        } else if (msg.type === "done") {
          const data = msg.data
          setAcceptanceRate(data.acceptance_rate * 100)
          acceptedDraftTokens.current = data.draft_tokens_accepted
          updateLiveSavingsFromAcceptedTokens()

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

  useEffect(() => {
    warmupDraftModel()
  }, [])

  useEffect(() => {
    return () => {
      if (cleanupRef.current) cleanupRef.current()
    }
  }, [])

  return (
    <div className="flex flex-1 gap-0 overflow-hidden">
      <div className="flex flex-1 flex-col overflow-hidden">
        <div className="shrink-0 border-b border-border/30 px-4 py-3">
          <NetworkVisualizer phase={phase} packets={packets} onPacketDone={handlePacketDone} />
        </div>

        <div className="flex flex-1 flex-col gap-3 overflow-hidden p-4">
          <ChatPanel prompt={prompt} tokens={visibleTokens} done={done} counts={counts} />
          <ChatInput onSubmit={handleSubmit} disabled={isStreaming} />
        </div>
      </div>

      <div className="flex shrink-0 flex-col border-l border-border/30">
        <button
          type="button"
          onClick={() => setSidebarOpen((prev) => !prev)}
          className="flex h-10 w-10 items-center justify-center text-muted-foreground transition-colors hover:bg-secondary/50 hover:text-foreground"
          aria-label={sidebarOpen ? "Close metrics sidebar" : "Open metrics sidebar"}
        >
          {sidebarOpen ? <PanelRightClose className="h-4 w-4" /> : <PanelRightOpen className="h-4 w-4" />}
        </button>
      </div>

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
