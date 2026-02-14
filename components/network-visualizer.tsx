"use client"

import { motion } from "framer-motion"

export type NetworkPhase = "idle" | "drafting" | "verifying" | "correcting" | "complete"

const phaseColor: Record<NetworkPhase, string> = {
  idle: "hsl(240, 5%, 35%)",
  drafting: "hsl(142, 71%, 45%)",
  verifying: "hsl(48, 96%, 53%)",
  correcting: "hsl(217, 91%, 60%)",
  complete: "hsl(142, 71%, 45%)",
}

/* ── Animated packet (a dot that travels across the connection lane) ── */
function Packet({
  direction,
  delay,
  active,
  color,
}: {
  direction: "ltr" | "rtl"
  delay: number
  active: boolean
  color: string
}) {
  const from = direction === "ltr" ? "0%" : "100%"
  const to = direction === "ltr" ? "100%" : "0%"

  return (
    <motion.div
      className="absolute top-1/2 h-2 w-2 -translate-y-1/2 rounded-full"
      style={{ backgroundColor: color }}
      initial={{ left: from, opacity: 0 }}
      animate={
        active
          ? {
              left: [from, to],
              opacity: [0, 1, 1, 0],
            }
          : { left: from, opacity: 0 }
      }
      transition={{
        duration: 1.6,
        delay,
        repeat: active ? Infinity : 0,
        repeatDelay: 0.5,
        ease: "easeInOut",
      }}
    />
  )
}

/* ── Node card (Edge or Cloud) ── */
function NodeBox({
  label,
  sublabel,
  phase,
  strokeColor,
}: {
  label: string
  sublabel: string
  phase: NetworkPhase
  strokeColor: string
}) {
  const isActive = phase !== "idle"

  return (
    <motion.div
      className="relative flex w-32 shrink-0 flex-col items-center justify-center rounded-xl border-2 px-3 py-4 md:w-40 lg:w-48"
      style={{
        backgroundColor: "hsl(240, 6%, 8%)",
        borderColor: strokeColor,
      }}
      animate={{ borderColor: strokeColor }}
      transition={{ duration: 0.3 }}
    >
      {/* Outer glow */}
      {isActive && (
        <motion.div
          className="pointer-events-none absolute inset-0 rounded-xl"
          style={{
            boxShadow: `0 0 20px 4px ${strokeColor}`,
          }}
          animate={{ opacity: [0.05, 0.15, 0.05] }}
          transition={{ duration: 2, repeat: Infinity }}
        />
      )}

      {/* Status dot */}
      <motion.div
        className="absolute left-3 top-3 h-2 w-2 rounded-full"
        style={{ backgroundColor: phaseColor[phase] }}
        animate={
          isActive
            ? { scale: [1, 1.5, 1] }
            : { scale: 1 }
        }
        transition={{ duration: 1.2, repeat: Infinity }}
      />

      <span
        className="font-heading text-[11px] font-bold tracking-wide md:text-xs"
        style={{ color: strokeColor }}
      >
        {label}
      </span>
      <span className="mt-0.5 font-mono text-[9px] text-muted-foreground md:text-[10px]">
        {sublabel}
      </span>
    </motion.div>
  )
}

/* ── Connection lane (the stretchy middle area between nodes) ── */
function ConnectionLane({
  phase,
}: {
  phase: NetworkPhase
}) {
  const lineOpacity = phase === "idle" ? 0.12 : 0.4
  const draftActive = phase === "drafting" || phase === "correcting"
  const verifyActive = phase === "verifying" || phase === "drafting"
  const draftColor =
    phase === "correcting" ? "hsl(217, 91%, 60%)" : "hsl(142, 71%, 45%)"
  const verifyColor =
    phase === "verifying" ? "hsl(48, 96%, 53%)" : "hsl(217, 91%, 60%)"

  return (
    <div className="relative flex flex-1 flex-col justify-center gap-5">
      {/* Draft lane: Edge -> Cloud */}
      <div className="relative flex items-center">
        <span className="absolute -top-3.5 left-1/2 -translate-x-1/2 text-[9px] text-muted-foreground/60 md:text-[10px]">
          Draft Tokens
        </span>
        <motion.div
          className="h-px w-full"
          style={{
            backgroundImage: `repeating-linear-gradient(to right, hsl(142, 71%, 45%) 0px, hsl(142, 71%, 45%) 6px, transparent 6px, transparent 12px)`,
          }}
          animate={{ opacity: lineOpacity }}
          transition={{ duration: 0.3 }}
        />
        {/* Arrow */}
        <div
          className="ml-[-6px] h-0 w-0 shrink-0 border-y-[4px] border-l-[6px] border-y-transparent"
          style={{ borderLeftColor: `hsl(142, 71%, 45%)`, opacity: lineOpacity }}
        />
        {/* Packets */}
        <div className="absolute inset-0">
          <Packet direction="ltr" delay={0} active={draftActive} color={draftColor} />
          <Packet direction="ltr" delay={0.7} active={draftActive} color={draftColor} />
          <Packet direction="ltr" delay={1.4} active={draftActive} color={draftColor} />
        </div>
      </div>

      {/* Verify lane: Cloud -> Edge */}
      <div className="relative flex items-center">
        <span className="absolute -bottom-3.5 left-1/2 -translate-x-1/2 text-[9px] text-muted-foreground/60 md:text-[10px]">
          Verified Tokens
        </span>
        {/* Arrow */}
        <div
          className="mr-[-6px] h-0 w-0 shrink-0 border-y-[4px] border-r-[6px] border-y-transparent"
          style={{ borderRightColor: `hsl(217, 91%, 60%)`, opacity: lineOpacity }}
        />
        <motion.div
          className="h-px w-full"
          style={{
            backgroundImage: `repeating-linear-gradient(to right, hsl(217, 91%, 60%) 0px, hsl(217, 91%, 60%) 6px, transparent 6px, transparent 12px)`,
          }}
          animate={{ opacity: lineOpacity }}
          transition={{ duration: 0.3 }}
        />
        {/* Packets */}
        <div className="absolute inset-0">
          <Packet direction="rtl" delay={0.3} active={verifyActive} color={verifyColor} />
          <Packet direction="rtl" delay={1.1} active={verifyActive} color={verifyColor} />
        </div>
      </div>
    </div>
  )
}

/* ── Main export ── */
interface NetworkVisualizerProps {
  phase: NetworkPhase
}

export function NetworkVisualizer({ phase }: NetworkVisualizerProps) {
  const edgeStroke =
    phase === "drafting" || phase === "correcting"
      ? "hsl(142, 71%, 45%)"
      : phase === "verifying"
        ? "hsl(48, 96%, 53%)"
        : phase === "complete"
          ? "hsl(142, 71%, 45%)"
          : "hsl(240, 5%, 25%)"

  const cloudStroke =
    phase === "verifying"
      ? "hsl(48, 96%, 53%)"
      : phase === "correcting"
        ? "hsl(217, 91%, 60%)"
        : phase === "drafting"
          ? "hsl(217, 91%, 60%)"
          : phase === "complete"
            ? "hsl(142, 71%, 45%)"
            : "hsl(240, 5%, 25%)"

  return (
    <div className="flex w-full items-center gap-4 px-2 md:gap-6 md:px-4 lg:gap-8">
      <NodeBox label="Edge Draft" sublabel="RTX 3060" phase={phase} strokeColor={edgeStroke} />
      <ConnectionLane phase={phase} />
      <NodeBox label="Cloud Target" sublabel="H100" phase={phase} strokeColor={cloudStroke} />
    </div>
  )
}
