"use client"

import { useState, useRef, useCallback, useEffect } from "react"
import { motion } from "framer-motion"
import { Play, RotateCcw, Cpu, Cloud, Check, X, Zap } from "lucide-react"
import { cn } from "@/lib/utils"
import logData from "@/data/speculative-log.json"

/* ── Constants ── */
const GREEN = "hsl(142, 71%, 45%)"
const BLUE = "hsl(217, 91%, 60%)"
const YELLOW = "hsl(48, 96%, 53%)"
const DIM = "hsl(240, 5%, 25%)"

const DRAFT_COLORS = [
  { label: "Draft A", border: "border-emerald-500/40", bg: "bg-emerald-500/10", text: "text-emerald-300" },
  { label: "Draft B", border: "border-violet-500/40", bg: "bg-violet-500/10", text: "text-violet-300" },
  { label: "Draft C", border: "border-amber-500/40", bg: "bg-amber-500/10", text: "text-amber-300" },
]

/* ── Types ── */
type VisPhase = "idle" | "running" | "complete"
interface LogToken {
  text: string
  status: "accepted" | "rejected"
}

interface LogDraft {
  id: string
  tokens: LogToken[]
  accepted_count: number
}

interface LogRound {
  round_num: number
  verification_time_ms: number
  drafts: LogDraft[]
  chosen_draft: string
  correction: { text: string } | null
}

interface LogData {
  prompt: string
  rounds: LogRound[]
  summary: {
    total_tokens: number
    draft_tokens_generated: number
    draft_tokens_accepted: number
    acceptance_rate: number
    speculation_rounds: number
    generation_time_ms: number
  }
}

interface RoundStats {
  round_num: number
  drafted: number
  accepted: number
  verification_time_ms: number
  chosen_draft: string
}

/* ── Sub-components ── */

function NodePanel({
  label,
  sublabel,
  icon: Icon,
  active,
  color,
  children,
}: {
  label: string
  sublabel: string
  icon: React.ElementType
  active: boolean
  color: string
  children?: React.ReactNode
}) {
  return (
    <motion.div
      className={cn(
        "relative flex w-64 shrink-0 flex-col rounded-2xl border-2 p-4",
        "bg-card/60 backdrop-blur-sm",
      )}
      style={{ borderColor: active ? color : DIM }}
      animate={{ borderColor: active ? color : DIM }}
      transition={{ duration: 0.3 }}
    >
      {active && (
        <motion.div
          className="pointer-events-none absolute inset-0 rounded-2xl"
          style={{ boxShadow: `0 0 30px 6px ${color}` }}
          animate={{ opacity: [0.03, 0.12, 0.03] }}
          transition={{ duration: 2, repeat: Infinity }}
        />
      )}
      <div className="mb-3 flex items-center gap-2">
        <div
          className="flex h-8 w-8 items-center justify-center rounded-lg"
          style={{ backgroundColor: `${color}20` }}
        >
          <Icon className="h-4 w-4" style={{ color }} />
        </div>
        <div>
          <div className="font-heading text-xs font-bold" style={{ color }}>
            {label}
          </div>
          <div className="font-mono text-[10px] text-muted-foreground">{sublabel}</div>
        </div>
        {active && (
          <motion.div
            className="ml-auto h-2 w-2 rounded-full"
            style={{ backgroundColor: color }}
            animate={{ scale: [1, 1.5, 1] }}
            transition={{ duration: 1, repeat: Infinity }}
          />
        )}
      </div>
      <div className="min-h-[300px]">{children}</div>
    </motion.div>
  )
}

function TokenPill({
  text,
  variant,
  animateIn,
  showIcon,
  iconType,
}: {
  text: string
  variant: "neutral" | "accepted" | "rejected" | "corrected" | "dimmed"
  animateIn?: boolean
  showIcon?: boolean
  iconType?: "accepted" | "rejected" | "corrected"
}) {
  const bg =
    variant === "neutral"
      ? "bg-green-500/10 border-green-500/25 text-green-200"
      : variant === "accepted"
        ? "bg-green-500/20 border-green-500/40 text-green-300"
        : variant === "rejected"
          ? "bg-red-500/20 border-red-500/40 text-red-300"
          : variant === "corrected"
            ? "bg-blue-500/20 border-blue-500/40 text-blue-300"
            : "bg-muted/20 border-muted/30 text-muted-foreground/50"

  const icon =
    iconType === "accepted" ? (
      <Check className="h-2.5 w-2.5 text-green-400" />
    ) : iconType === "rejected" ? (
      <X className="h-2.5 w-2.5 text-red-400" />
    ) : iconType === "corrected" ? (
      <Zap className="h-2.5 w-2.5 text-blue-400" />
    ) : null

  return (
    <motion.span
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 font-mono text-[11px]",
        bg,
      )}
      initial={animateIn ? { opacity: 0, scale: 0.5, y: 8 } : false}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      transition={{ duration: 0.25, type: "spring", stiffness: 400 }}
    >
      {showIcon && icon}
      {text}
    </motion.span>
  )
}

function DraftRow({
  draftIndex,
  tokens,
}: {
  draftIndex: number
  tokens: { text: string }[]
}) {
  const style = DRAFT_COLORS[draftIndex]
  return (
    <div className={cn("flex items-start gap-1.5 rounded-lg border px-2 py-1.5", style.border, style.bg)}>
      <span className={cn("mt-0.5 shrink-0 text-[9px] font-bold uppercase tracking-wider", style.text)}>
        {style.label}
      </span>
      <div className="flex flex-wrap gap-0.5">
        {tokens.map((tok, i) => (
          <motion.span
            key={i}
            className={cn("rounded px-1 py-0.5 font-mono text-[10px]", style.text, "bg-white/5")}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05, duration: 0.2 }}
          >
            {tok.text}
          </motion.span>
        ))}
      </div>
    </div>
  )
}

function VerifyRow({
  draftIndex,
  tokens,
  isWinner,
  acceptedCount,
  correction,
}: {
  draftIndex: number
  tokens: LogToken[]
  isWinner: boolean
  acceptedCount: number
  correction: { text: string } | null
}) {
  const style = DRAFT_COLORS[draftIndex]
  return (
    <motion.div
      className={cn(
        "flex items-start gap-1.5 rounded-lg border px-2 py-1.5",
        isWinner ? "border-green-500/40 bg-green-500/10" : "border-muted/30 bg-muted/5",
      )}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2 }}
    >
      <div className="flex shrink-0 flex-col items-center gap-0.5">
        <span className={cn("text-[9px] font-bold uppercase tracking-wider", style.text)}>
          {style.label}
        </span>
        <span className={cn(
          "rounded px-1 font-mono text-[9px] font-bold",
          isWinner ? "bg-green-500/20 text-green-400" : "bg-muted/20 text-muted-foreground",
        )}>
          {acceptedCount}/{tokens.length}
        </span>
      </div>
      <div className="flex flex-wrap gap-0.5">
        {tokens.map((tok, i) => (
          <TokenPill
            key={i}
            text={tok.text}
            variant={tok.status === "accepted" ? "accepted" : "rejected"}
            showIcon
            iconType={tok.status === "accepted" ? "accepted" : "rejected"}
            animateIn
          />
        ))}
        {isWinner && correction && (
          <TokenPill
            text={correction.text}
            variant="corrected"
            showIcon
            iconType="corrected"
            animateIn
          />
        )}
      </div>
    </motion.div>
  )
}

function StatsBar({ rounds }: { rounds: RoundStats[] }) {
  const latest = rounds[rounds.length - 1]
  if (!latest) return null

  const totalDrafted = rounds.reduce((s, r) => s + r.drafted, 0)
  const totalAccepted = rounds.reduce((s, r) => s + r.accepted, 0)
  const overallRate = totalDrafted > 0 ? (totalAccepted / totalDrafted) * 100 : 0

  return (
    <motion.div
      className="flex flex-wrap items-center justify-center gap-4 rounded-xl border border-border/50 bg-card/40 px-4 py-2 text-xs backdrop-blur-sm"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
    >
      <div className="flex items-center gap-1.5">
        <span className="text-muted-foreground">Round</span>
        <span className="font-mono font-bold text-foreground">{latest.round_num}</span>
      </div>
      <div className="h-3 w-px bg-border/50" />
      <div className="flex items-center gap-1.5">
        <span className="text-muted-foreground">Best Draft</span>
        <span className="font-mono font-bold text-yellow-400">{latest.chosen_draft.toUpperCase()}</span>
      </div>
      <div className="h-3 w-px bg-border/50" />
      <div className="flex items-center gap-1.5">
        <span className="text-muted-foreground">Accepted</span>
        <span className="font-mono font-bold text-green-400">{totalAccepted}</span>
      </div>
      <div className="h-3 w-px bg-border/50" />
      <div className="flex items-center gap-1.5">
        <span className="text-muted-foreground">Rate</span>
        <span className="font-mono font-bold text-yellow-400">{overallRate.toFixed(0)}%</span>
      </div>
      <div className="h-3 w-px bg-border/50" />
      <div className="flex items-center gap-1.5">
        <span className="text-muted-foreground">Verify</span>
        <span className="font-mono font-bold text-blue-400">
          {latest.verification_time_ms.toFixed(0)}ms
        </span>
      </div>
    </motion.div>
  )
}

/* ── Animation stage for each round ── */
type RoundAnimStage = "idle" | "drafting" | "flying" | "verifying" | "choosing" | "done"

interface RoundAnimState {
  roundNum: number
  stage: RoundAnimStage
  round: LogRound
}

/* ── Main export ── */
export function SpeculativeVisualizer() {
  const data = logData as LogData

  const [phase, setPhase] = useState<VisPhase>("idle")
  const [currentRound, setCurrentRound] = useState<RoundAnimState | null>(null)
  const [rounds, setRounds] = useState<RoundStats[]>([])
  const [resultTokens, setResultTokens] = useState<{ text: string; type: string }[]>([])
  const [finalStats, setFinalStats] = useState<LogData["summary"] | null>(null)

  const cancelledRef = useRef(false)
  const timeoutsRef = useRef<ReturnType<typeof setTimeout>[]>([])

  const reset = useCallback(() => {
    cancelledRef.current = true
    timeoutsRef.current.forEach(clearTimeout)
    timeoutsRef.current = []
    setPhase("idle")
    setCurrentRound(null)
    setRounds([])
    setResultTokens([])
    setFinalStats(null)
  }, [])

  const schedule = useCallback((fn: () => void, delay: number) => {
    const id = setTimeout(() => {
      if (!cancelledRef.current) fn()
    }, delay)
    timeoutsRef.current.push(id)
  }, [])

  const startVisualization = useCallback(() => {
    reset()
    setTimeout(() => {
      cancelledRef.current = false
      setPhase("running")

      let globalDelay = 0
      const DRAFT_PHASE = 400      // time to show drafts appearing
      const FLY_PHASE = 400        // flying animation
      const VERIFY_PHASE = 250     // show all verdicts at once
      const CORRECTION_DELAY = 300 // extra delay for correction token
      const CHOOSE_PHASE = 500     // highlight winner
      const ROUND_GAP = 250        // pause between rounds

      data.rounds.forEach((round) => {
        const chosenDraft = round.drafts.find((d) => d.id === round.chosen_draft)!
        const hasCorrection = round.correction !== null

        // Stage: drafting — show 3 draft rows in draft node
        schedule(() => {
          setCurrentRound({ roundNum: round.round_num, stage: "drafting", round })
        }, globalDelay)

        globalDelay += DRAFT_PHASE

        // Stage: flying — tokens in transit
        schedule(() => {
          setCurrentRound({ roundNum: round.round_num, stage: "flying", round })
        }, globalDelay)

        globalDelay += FLY_PHASE

        // Stage: verifying — show verdicts at target (all at once for accepted/rejected)
        schedule(() => {
          setCurrentRound({ roundNum: round.round_num, stage: "verifying", round })
        }, globalDelay)

        globalDelay += VERIFY_PHASE

        // If there's a correction, wait extra for it to appear autoregressively
        if (hasCorrection) {
          globalDelay += CORRECTION_DELAY
        }

        // Stage: choosing — highlight the winner
        schedule(() => {
          setCurrentRound({ roundNum: round.round_num, stage: "choosing", round })
        }, globalDelay)

        globalDelay += CHOOSE_PHASE

        // Stage: done — add to result, emit stats
        schedule(() => {
          setCurrentRound({ roundNum: round.round_num, stage: "done", round })

          // Add accepted tokens from winner + correction to result
          chosenDraft.tokens.forEach((tok) => {
            if (tok.status === "accepted") {
              setResultTokens((prev) => [...prev, { text: tok.text, type: "accepted" }])
            }
          })
          if (round.correction) {
            setResultTokens((prev) => [...prev, { text: round.correction!.text, type: "corrected" }])
          }

          setRounds((prev) => [
            ...prev,
            {
              round_num: round.round_num,
              drafted: chosenDraft.tokens.length * round.drafts.length,
              accepted: chosenDraft.accepted_count + (round.correction ? 1 : 0),
              verification_time_ms: round.verification_time_ms,
              chosen_draft: round.chosen_draft,
            },
          ])
        }, globalDelay)

        globalDelay += ROUND_GAP
      })

      // Complete
      schedule(() => {
        setCurrentRound(null)
        setFinalStats(data.summary)
        setPhase("complete")
      }, globalDelay + 1000)
    }, 50)
  }, [reset, data, schedule])

  useEffect(() => {
    return () => {
      cancelledRef.current = true
      timeoutsRef.current.forEach(clearTimeout)
    }
  }, [])

  const isDraftActive = currentRound?.stage === "drafting" || currentRound?.stage === "flying"
  const isTargetActive = currentRound?.stage === "verifying" || currentRound?.stage === "choosing"
  const isFlying = currentRound?.stage === "flying"

  return (
    <div className="flex flex-1 flex-col items-center gap-6 overflow-y-auto px-6 py-8">
      {/* Title */}
      <div className="text-center">
        <h2 className="font-heading text-xl font-bold tracking-tight text-foreground">
          Speculative Decoding Visualizer
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Draft model generates 3 candidate sequences and target picks the longest match
        </p>
      </div>

      {/* Fixed prompt display */}
      <div className="w-full max-w-3xl rounded-xl border border-border/50 bg-card/40 px-4 py-3 backdrop-blur-sm">
        <div className="mb-1 text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
          Prompt
        </div>
        <div className="font-mono text-sm text-foreground">{data.prompt}</div>
      </div>

      {/* Main visualization area */}
      <div className="flex w-full max-w-5xl items-stretch gap-0">
        {/* Draft node */}
        <NodePanel
          label="Draft Node"
          sublabel="Qwen 1.5B · RTX 3060"
          icon={Cpu}
          active={!!isDraftActive}
          color={GREEN}
        >
          {currentRound && (currentRound.stage === "drafting") && (
            <div className="flex flex-col gap-1.5">
              {currentRound.round.drafts.map((draft, i) => (
                <motion.div
                  key={draft.id}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.06, duration: 0.2 }}
                >
                  <DraftRow
                    draftIndex={i}
                    tokens={draft.tokens}
                  />
                </motion.div>
              ))}
            </div>
          )}
          {currentRound && currentRound.stage === "flying" && (
            <div className="flex flex-col gap-1.5 opacity-30">
              {currentRound.round.drafts.map((draft, i) => (
                <DraftRow key={draft.id} draftIndex={i} tokens={draft.tokens} />
              ))}
            </div>
          )}
          {phase === "running" && !currentRound && (
            <span className="text-[10px] text-muted-foreground/60">Waiting...</span>
          )}
          {phase === "running" && currentRound && currentRound.stage !== "drafting" && currentRound.stage !== "flying" && (
            <span className="text-[10px] text-muted-foreground/60">Waiting for next round...</span>
          )}
        </NodePanel>

        {/* Connection lane */}
        <div className="relative flex flex-1 flex-col justify-center px-2">
          <div className="absolute -top-4 left-1/2 -translate-x-1/2 whitespace-nowrap text-[9px] font-medium uppercase tracking-widest text-muted-foreground/50">
            Token Transfer
          </div>

          {/* 3 draft lanes */}
          {[0, 1, 2].map((i) => (
            <div key={i} className="relative mb-3 flex items-center">
              {i === 0 && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 text-[9px] text-green-400/60">
                  3 Draft Batches →
                </span>
              )}
              <motion.div
                className="h-px w-full"
                style={{
                  backgroundImage: `repeating-linear-gradient(to right, ${GREEN} 0px, ${GREEN} 4px, transparent 4px, transparent 10px)`,
                }}
                animate={{ opacity: isDraftActive ? 0.4 : 0.08 }}
                transition={{ duration: 0.3 }}
              />
              <div
                className="ml-[-5px] h-0 w-0 shrink-0 border-y-[3px] border-l-[5px] border-y-transparent"
                style={{ borderLeftColor: GREEN, opacity: isDraftActive ? 0.5 : 0.1 }}
              />
              {/* Flying dot */}
              {isFlying && (
                <motion.div
                  className="absolute top-1/2 h-2 w-2 -translate-y-1/2 rounded-full"
                  style={{ backgroundColor: GREEN, boxShadow: `0 0 8px 2px ${GREEN}` }}
                  initial={{ left: "0%", opacity: 0, scale: 0.5 }}
                  animate={{ left: "100%", opacity: [0, 1, 1, 0], scale: [0.5, 1.2, 1, 0.5] }}
                  transition={{ duration: 0.4, ease: "easeInOut" }}
                />
              )}
            </div>
          ))}

          {/* Return lane */}
          <div className="relative mt-1 flex items-center">
            <span className="absolute -bottom-3 left-1/2 -translate-x-1/2 text-[9px] text-blue-400/60">
              ← Best Sequence
            </span>
            <div
              className="mr-[-5px] h-0 w-0 shrink-0 border-y-[3px] border-r-[5px] border-y-transparent"
              style={{ borderRightColor: BLUE, opacity: isTargetActive ? 0.5 : 0.1 }}
            />
            <motion.div
              className="h-px w-full"
              style={{
                backgroundImage: `repeating-linear-gradient(to right, ${BLUE} 0px, ${BLUE} 4px, transparent 4px, transparent 10px)`,
              }}
              animate={{ opacity: isTargetActive ? 0.4 : 0.08 }}
              transition={{ duration: 0.3 }}
            />
          </div>
        </div>

        {/* Target node */}
        <NodePanel
          label="Target Node"
          sublabel="Qwen 7B · H100"
          icon={Cloud}
          active={!!isTargetActive}
          color={YELLOW}
        >
          {currentRound && (currentRound.stage === "verifying" || currentRound.stage === "choosing") && (
            <div className="flex flex-col gap-1.5">
              {currentRound.round.drafts.map((draft, i) => (
                <motion.div
                  key={draft.id}
                  initial={{ opacity: 0, x: 10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.2 }}
                >
                  <VerifyRow
                    draftIndex={i}
                    tokens={draft.tokens}
                    isWinner={currentRound.stage === "choosing" && draft.id === currentRound.round.chosen_draft}
                    acceptedCount={draft.accepted_count}
                    correction={draft.id === currentRound.round.chosen_draft ? currentRound.round.correction : null}
                  />
                </motion.div>
              ))}
            </div>
          )}
          {phase === "running" && currentRound && currentRound.stage !== "verifying" && currentRound.stage !== "choosing" && (
            <span className="text-[10px] text-muted-foreground/60">Waiting for tokens...</span>
          )}
        </NodePanel>
      </div>

      {/* Stats bar */}
      {rounds.length > 0 && <StatsBar rounds={rounds} />}

      {/* Result text */}
      {resultTokens.length > 0 && (
        <motion.div
          className="w-full max-w-3xl rounded-xl border border-border/50 bg-card/40 px-4 py-3 backdrop-blur-sm"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <div className="mb-2 text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
            Generated Output
          </div>
          <p className="font-mono text-sm leading-relaxed whitespace-pre-wrap">
            {resultTokens.map((t, i) => (
              <span
                key={i}
                className={cn(
                  "transition-colors",
                  t.type === "accepted"
                    ? "text-green-300"
                    : t.type === "corrected"
                      ? "text-blue-300"
                      : "text-foreground",
                )}
              >
                {t.text}
              </span>
            ))}
            {phase === "running" && (
              <motion.span
                className="inline-block h-4 w-1.5 rounded-sm bg-foreground/60"
                animate={{ opacity: [1, 0, 1] }}
                transition={{ duration: 0.8, repeat: Infinity }}
              />
            )}
          </p>
        </motion.div>
      )}

      {/* Final stats */}
      {phase === "complete" && finalStats && (
        <motion.div
          className="w-full max-w-3xl rounded-xl border border-green-500/30 bg-green-500/5 px-4 py-3"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <div className="mb-2 text-[10px] font-medium uppercase tracking-widest text-green-400">
            Complete
          </div>
          <div className="grid grid-cols-3 gap-4 text-center">
            <div>
              <div className="font-mono text-lg font-bold text-foreground">
                {finalStats.total_tokens}
              </div>
              <div className="text-[10px] text-muted-foreground">Total Tokens</div>
            </div>
            <div>
              <div className="font-mono text-lg font-bold text-green-400">
                {(finalStats.acceptance_rate * 100).toFixed(0)}%
              </div>
              <div className="text-[10px] text-muted-foreground">Acceptance Rate</div>
            </div>
            <div>
              <div className="font-mono text-lg font-bold text-blue-400">
                {finalStats.speculation_rounds}
              </div>
              <div className="text-[10px] text-muted-foreground">Rounds</div>
            </div>
          </div>
        </motion.div>
      )}

      {/* Start / Restart button */}
      <motion.button
        className={cn(
          "flex items-center gap-2 rounded-xl px-6 py-3 font-heading text-sm font-bold tracking-wide transition-colors",
          phase === "running"
            ? "cursor-not-allowed border border-border/50 bg-card/40 text-muted-foreground"
            : "bg-primary text-primary-foreground hover:bg-primary/90",
        )}
        onClick={phase === "running" ? undefined : startVisualization}
        disabled={phase === "running"}
        whileHover={phase !== "running" ? { scale: 1.03 } : {}}
        whileTap={phase !== "running" ? { scale: 0.97 } : {}}
      >
        {phase === "idle" && (
          <>
            <Play className="h-4 w-4" />
            Start Visualization
          </>
        )}
        {phase === "running" && (
          <>
            <motion.div
              className="h-4 w-4 rounded-full border-2 border-current border-t-transparent"
              animate={{ rotate: 360 }}
              transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
            />
            Running...
          </>
        )}
        {phase === "complete" && (
          <>
            <RotateCcw className="h-4 w-4" />
            Restart
          </>
        )}
      </motion.button>
    </div>
  )
}
