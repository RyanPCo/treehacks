"use client"

import { useEffect, useState, useRef, useCallback, createContext, useContext } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { User, Bot, CheckCircle2, XCircle, RefreshCw } from "lucide-react"

// ── Shared Context for status synchronization ──
interface StreamStatus {
  phase: "idle" | "drafting" | "verifying" | "correcting" | "complete"
  currentToken: string
  counts: { accepted: number; rejected: number; corrected: number; drafted: number }
}

const StreamStatusContext = createContext<StreamStatus>({
  phase: "idle",
  currentToken: "",
  counts: { accepted: 0, rejected: 0, corrected: 0, drafted: 0 },
})

export function useStreamStatus() {
  return useContext(StreamStatusContext)
}

// ── Token types ──
type TokenType = "accepted" | "rejected" | "corrected"

interface Token {
  text: string
  type: TokenType
}

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

interface VisibleToken {
  text: string
  type: TokenType
  phase: "appearing" | "striking" | "struck" | "hidden" | "settled"
}

// ── Status event log ──
interface StatusEvent {
  id: number
  type: "draft" | "verified" | "rejected" | "corrected"
  token: string
  timestamp: number
}

export function ChatStream() {
  const [visibleTokens, setVisibleTokens] = useState<VisibleToken[]>([])
  const [done, setDone] = useState(false)
  const [counts, setCounts] = useState({ accepted: 0, rejected: 0, corrected: 0, drafted: 0 })
  const [status, setStatus] = useState<StreamStatus>({
    phase: "idle",
    currentToken: "",
    counts: { accepted: 0, rejected: 0, corrected: 0, drafted: 0 },
  })
  const [statusEvents, setStatusEvents] = useState<StatusEvent[]>([])
  const eventIdRef = useRef(0)
  const scrollRef = useRef<HTMLDivElement>(null)
  const stepIdx = useRef(0)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const scrollToBottom = useCallback(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [])

  const addEvent = useCallback((type: StatusEvent["type"], token: string) => {
    eventIdRef.current += 1
    setStatusEvents(prev => {
      const next = [...prev, { id: eventIdRef.current, type, token, timestamp: Date.now() }]
      return next.slice(-5) // Keep last 5 events
    })
  }, [])

  useEffect(() => {
    function processStep() {
      if (stepIdx.current >= STEPS.length) {
        setDone(true)
        setStatus(prev => ({ ...prev, phase: "complete" }))
        return
      }

      const step = STEPS[stepIdx.current]
      stepIdx.current += 1

      if (step.kind === "accepted") {
        setVisibleTokens(prev => [...prev, { text: step.token.text, type: step.token.type, phase: "settled" }])
        setCounts(prev => {
          const next = {
            ...prev,
            drafted: prev.drafted + 1,
            ...(step.token.type === "accepted" ? { accepted: prev.accepted + 1 } : {}),
            ...(step.token.type === "corrected" ? { corrected: prev.corrected + 1 } : {}),
          }
          setStatus({ phase: "drafting", currentToken: step.token.text.trim(), counts: next })
          return next
        })
        addEvent("draft", step.token.text.trim())
        addEvent("verified", step.token.text.trim())
        scrollToBottom()
        timeoutRef.current = setTimeout(processStep, ACCEPTED_DELAY)
      } else {
        // Drafting phase
        setStatus(prev => ({ ...prev, phase: "drafting", currentToken: step.rejected.text.trim() }))
        addEvent("draft", step.rejected.text.trim())
        setVisibleTokens(prev => [
          ...prev,
          { text: step.rejected.text, type: "rejected", phase: "appearing" },
        ])
        setCounts(prev => ({ ...prev, drafted: prev.drafted + 1 }))
        scrollToBottom()

        // Verifying -> Rejected
        timeoutRef.current = setTimeout(() => {
          setStatus(prev => ({ ...prev, phase: "verifying", currentToken: step.rejected.text.trim() }))
          setVisibleTokens(prev => {
            const copy = [...prev]
            const last = copy[copy.length - 1]
            copy[copy.length - 1] = { ...last, phase: "striking" }
            return copy
          })
          setCounts(prev => {
            const next = { ...prev, rejected: prev.rejected + 1 }
            setStatus({ phase: "verifying", currentToken: step.rejected.text.trim(), counts: next })
            return next
          })
          addEvent("rejected", step.rejected.text.trim())

          // Correcting phase
          timeoutRef.current = setTimeout(() => {
            setVisibleTokens(prev => {
              const copy = [...prev]
              copy[copy.length - 1] = { ...copy[copy.length - 1], phase: "hidden" }
              return copy
            })

            timeoutRef.current = setTimeout(() => {
              setStatus(prev => ({ ...prev, phase: "correcting", currentToken: step.corrected.text.trim() }))
              addEvent("corrected", step.corrected.text.trim())
              setVisibleTokens(prev => {
                const withoutHidden = prev.filter(t => t.phase !== "hidden")
                return [
                  ...withoutHidden,
                  { text: step.corrected.text, type: "corrected", phase: "appearing" },
                ]
              })
              setCounts(prev => {
                const next = { ...prev, drafted: prev.drafted + 1, corrected: prev.corrected + 1 }
                setStatus({ phase: "correcting", currentToken: step.corrected.text.trim(), counts: next })
                return next
              })
              scrollToBottom()

              timeoutRef.current = setTimeout(() => {
                setVisibleTokens(prev => {
                  const copy = [...prev]
                  copy[copy.length - 1] = { ...copy[copy.length - 1], phase: "settled" }
                  return copy
                })
                setStatus(prev => ({ ...prev, phase: "drafting" }))
                timeoutRef.current = setTimeout(processStep, ACCEPTED_DELAY)
              }, 150)
            }, 100)
          }, STRIKE_PAUSE)
        }, REJECTED_SHOW_DELAY)
      }
    }

    timeoutRef.current = setTimeout(processStep, INITIAL_DELAY)
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
    }
  }, [scrollToBottom, addEvent])

  return (
    <StreamStatusContext.Provider value={status}>
      <Card className="flex h-full flex-col border-border/50 bg-card/50 backdrop-blur-sm">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center justify-between text-sm font-medium text-muted-foreground">
            <span>Speculative Chat Stream</span>
            <div className="flex items-center gap-3 text-[10px]">
              <span className="flex items-center gap-1">
                <span className="inline-block h-2 w-2 rounded-full bg-green-400" />
                Accepted
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block h-2 w-2 rounded-full bg-red-500" />
                Rejected
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block h-2 w-2 rounded-full bg-blue-400" />
                Corrected
              </span>
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-1 flex-col gap-3 overflow-hidden">
          {/* Inline status bar */}
          <StatusBar status={status} events={statusEvents} />

          <ScrollArea className="flex-1 pr-4">
            <div className="flex flex-col gap-4" ref={scrollRef}>
              {/* User message */}
              <motion.div
                className="flex gap-3"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: 0.1 }}
              >
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-secondary">
                  <User className="h-4 w-4 text-foreground" />
                </div>
                <div className="flex flex-col gap-1">
                  <span className="text-xs font-medium text-muted-foreground">You</span>
                  <p className="text-sm leading-relaxed text-foreground">
                    Explain the theory of relativity.
                  </p>
                </div>
              </motion.div>

              {/* AI response */}
              <motion.div
                className="flex gap-3"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: 0.5 }}
              >
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 ring-1 ring-primary/20">
                  <Bot className="h-4 w-4 text-primary" />
                </div>
                <div className="flex flex-col gap-1">
                  <span className="text-xs font-medium text-muted-foreground">SpecNet</span>
                  <div className="rounded-lg bg-secondary/50 p-3">
                    <p className="font-mono text-sm leading-relaxed">
                      <AnimatePresence mode="popLayout">
                        {visibleTokens.map((vt, i) => (
                          <SpecToken key={`${i}-${vt.text}-${vt.type}`} token={vt} />
                        ))}
                      </AnimatePresence>
                      {!done && (
                        <span className="ml-0.5 inline-block h-4 w-[2px] animate-pulse bg-foreground align-middle" />
                      )}
                    </p>
                  </div>
                  <div className="mt-2 flex items-center gap-4 text-[10px] text-muted-foreground tabular-nums">
                    <span>{counts.drafted} tokens drafted</span>
                    <span className="text-green-400">{counts.accepted} accepted</span>
                    <span className="text-red-500">{counts.rejected} rejected</span>
                    <span className="text-blue-400">{counts.corrected} corrected</span>
                  </div>
                </div>
              </motion.div>
            </div>
          </ScrollArea>
        </CardContent>
      </Card>
    </StreamStatusContext.Provider>
  )
}

// ── Inline status bar showing real-time draft/verify state ──
function StatusBar({ status, events }: { status: StreamStatus; events: StatusEvent[] }) {
  const phaseConfig: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
    idle: { label: "Waiting...", color: "text-muted-foreground", icon: null },
    drafting: { label: "Drafting", color: "text-green-400", icon: <CheckCircle2 className="h-3 w-3" /> },
    verifying: { label: "Verifying", color: "text-yellow-400", icon: <RefreshCw className="h-3 w-3 animate-spin" /> },
    correcting: { label: "Correcting", color: "text-blue-400", icon: <RefreshCw className="h-3 w-3" /> },
    complete: { label: "Complete", color: "text-green-400", icon: <CheckCircle2 className="h-3 w-3" /> },
  }

  const cfg = phaseConfig[status.phase] || phaseConfig.idle

  return (
    <div className="flex items-center gap-3 rounded-lg border border-border/30 bg-background/50 px-3 py-2">
      {/* Phase indicator */}
      <div className={`flex items-center gap-1.5 text-xs font-medium ${cfg.color}`}>
        {status.phase !== "idle" && status.phase !== "complete" && (
          <span className="relative flex h-2 w-2">
            <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-75 ${
              status.phase === "drafting" ? "bg-green-400" : status.phase === "verifying" ? "bg-yellow-400" : "bg-blue-400"
            }`} />
            <span className={`relative inline-flex h-2 w-2 rounded-full ${
              status.phase === "drafting" ? "bg-green-500" : status.phase === "verifying" ? "bg-yellow-500" : "bg-blue-500"
            }`} />
          </span>
        )}
        {status.phase === "complete" && cfg.icon}
        <span>{cfg.label}</span>
        {status.currentToken && status.phase !== "complete" && (
          <span className="font-mono text-foreground/70">
            {'"'}{status.currentToken}{'"'}
          </span>
        )}
      </div>

      {/* Separator */}
      <div className="h-3 w-px bg-border/50" />

      {/* Live event feed */}
      <div className="flex flex-1 items-center gap-2 overflow-hidden">
        <AnimatePresence mode="popLayout">
          {events.map(evt => (
            <motion.span
              key={evt.id}
              initial={{ opacity: 0, scale: 0.8, x: 10 }}
              animate={{ opacity: 1, scale: 1, x: 0 }}
              exit={{ opacity: 0, scale: 0.8 }}
              transition={{ duration: 0.15 }}
              className={`inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-medium ${
                evt.type === "draft"
                  ? "bg-green-500/10 text-green-400"
                  : evt.type === "verified"
                    ? "bg-green-500/10 text-green-300"
                    : evt.type === "rejected"
                      ? "bg-red-500/10 text-red-400"
                      : "bg-blue-500/10 text-blue-400"
              }`}
            >
              {evt.type === "draft" && <CheckCircle2 className="h-2.5 w-2.5" />}
              {evt.type === "verified" && <CheckCircle2 className="h-2.5 w-2.5" />}
              {evt.type === "rejected" && <XCircle className="h-2.5 w-2.5" />}
              {evt.type === "corrected" && <RefreshCw className="h-2.5 w-2.5" />}
              <span className="max-w-[60px] truncate font-mono">{evt.token}</span>
            </motion.span>
          ))}
        </AnimatePresence>
      </div>
    </div>
  )
}

function SpecToken({ token }: { token: VisibleToken }) {
  const base = getPhaseClass(token)

  return (
    <motion.span
      className={base}
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: token.phase === "hidden" ? 0 : 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.8, transition: { duration: 0.15 } }}
      transition={{ duration: 0.18, ease: "easeOut" as const }}
      layout
    >
      {token.text}
    </motion.span>
  )
}

function getPhaseClass(token: VisibleToken): string {
  if (token.type === "accepted") return "text-green-400"

  if (token.type === "rejected") {
    if (token.phase === "appearing") return "text-red-400"
    if (token.phase === "striking" || token.phase === "struck")
      return "text-red-500 line-through opacity-50 transition-all duration-300"
    return "text-red-500 line-through opacity-0"
  }

  if (token.type === "corrected") {
    if (token.phase === "appearing") return "text-blue-400 font-semibold scale-105 inline-block"
    return "text-blue-400 font-semibold"
  }

  return ""
}
