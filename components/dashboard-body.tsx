"use client"

import { useEffect, useState, useRef, useCallback } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { NetworkVisualizer, type NetworkPhase, type PacketEvent } from "@/components/network-visualizer"
import { ChatPanel, type VisibleToken } from "@/components/chat-panel"
import { ChatInput } from "@/components/chat-input"
import { LiveMetrics } from "@/components/live-metrics"
import { PanelRightOpen, PanelRightClose } from "lucide-react"

// ── Token data ──
type TokenType = "accepted" | "rejected" | "corrected"
interface Token { text: string; type: TokenType }

const tokenStream: Token[] = [
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

// ── Steps ──
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

const STEPS = buildSteps(tokenStream)
const ACCEPTED_DELAY = 60
const REJECTED_SHOW_DELAY = 80
const STRIKE_PAUSE = 500
const INITIAL_DELAY = 800

export function DashboardBody() {
  const [sidebarOpen, setSidebarOpen] = useState(true)

  // Shared state that drives BOTH the visualizer and the chat panel
  const [phase, setPhase] = useState<NetworkPhase>("idle")
  const [currentToken, setCurrentToken] = useState("")
  const [visibleTokens, setVisibleTokens] = useState<VisibleToken[]>([])
  const [done, setDone] = useState(false)
  const [counts, setCounts] = useState({ accepted: 0, rejected: 0, corrected: 0, drafted: 0 })
  const [packets, setPackets] = useState<PacketEvent[]>([])
  const packetId = useRef(0)
  const stepIdx = useRef(0)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const emitPacket = useCallback((lane: "draft" | "verify", color: string) => {
    const id = packetId.current++
    const direction = lane === "draft" ? "ltr" as const : "rtl" as const
    setPackets((prev) => [...prev, { id, direction, lane, color }])
  }, [])

  const handlePacketDone = useCallback((id: number) => {
    setPackets((prev) => prev.filter((p) => p.id !== id))
  }, [])

  const processStep = useCallback(() => {
    if (stepIdx.current >= STEPS.length) {
      setDone(true)
      setPhase("complete")
      setCurrentToken("")
      return
    }

    const step = STEPS[stepIdx.current]
    stepIdx.current += 1

    if (step.kind === "accepted") {
      setPhase("drafting")
      setCurrentToken(step.token.text.trim())
      emitPacket("draft", "hsl(142, 71%, 45%)")
      emitPacket("verify", "hsl(217, 91%, 60%)")
      setVisibleTokens(prev => [...prev, { text: step.token.text, type: step.token.type, phase: "settled" }])
      setCounts(prev => ({
        ...prev,
        drafted: prev.drafted + 1,
        accepted: step.token.type === "accepted" ? prev.accepted + 1 : prev.accepted,
        corrected: step.token.type === "corrected" ? prev.corrected + 1 : prev.corrected,
      }))
      timeoutRef.current = setTimeout(processStep, ACCEPTED_DELAY)
    } else {
      // Drafting the rejected token
      setPhase("drafting")
      setCurrentToken(step.rejected.text.trim())
      emitPacket("draft", "hsl(142, 71%, 45%)")
      setVisibleTokens(prev => [...prev, { text: step.rejected.text, type: "rejected", phase: "appearing" }])
      setCounts(prev => ({ ...prev, drafted: prev.drafted + 1 }))

      // Verifying -> rejected
      timeoutRef.current = setTimeout(() => {
        setPhase("verifying")
        setCurrentToken(step.rejected.text.trim())
        emitPacket("verify", "hsl(48, 96%, 53%)")
        setVisibleTokens(prev => {
          const copy = [...prev]
          copy[copy.length - 1] = { ...copy[copy.length - 1], phase: "striking" }
          return copy
        })
        setCounts(prev => ({ ...prev, rejected: prev.rejected + 1 }))

        // Correcting
        timeoutRef.current = setTimeout(() => {
          setVisibleTokens(prev => {
            const copy = [...prev]
            copy[copy.length - 1] = { ...copy[copy.length - 1], phase: "hidden" }
            return copy
          })

          timeoutRef.current = setTimeout(() => {
            setPhase("correcting")
            setCurrentToken(step.corrected.text.trim())
            emitPacket("draft", "hsl(217, 91%, 60%)")
            emitPacket("verify", "hsl(217, 91%, 60%)")
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
              timeoutRef.current = setTimeout(processStep, ACCEPTED_DELAY)
            }, 150)
          }, 100)
        }, STRIKE_PAUSE)
      }, REJECTED_SHOW_DELAY)
    }
  }, [emitPacket])

  useEffect(() => {
    timeoutRef.current = setTimeout(processStep, INITIAL_DELAY)
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
    }
  }, [processStep])

  return (
    <div className="flex flex-1 gap-0 overflow-hidden">
      {/* Main content area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Network visualizer strip -- synced to chat phase */}
        <div className="shrink-0 border-b border-border/30 px-4 py-3">
          <NetworkVisualizer phase={phase} packets={packets} onPacketDone={handlePacketDone} />
        </div>

        {/* Chat area */}
        <div className="flex flex-1 flex-col gap-3 overflow-hidden p-4">
          <ChatPanel tokens={visibleTokens} done={done} counts={counts} />
          <ChatInput />
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
              <LiveMetrics />
            </div>
          </motion.aside>
        )}
      </AnimatePresence>
    </div>
  )
}
