"use client"

import { motion } from "framer-motion"
import { Cpu, Server } from "lucide-react"

function AnimatedPacket({ delay }: { delay: number }) {
  return (
    <motion.circle
      cx="0"
      cy="0"
      r="3"
      fill="hsl(142, 71%, 45%)"
      initial={{ opacity: 0 }}
      animate={{
        opacity: [0, 1, 1, 0],
        cx: [60, 260],
        cy: [80, 80],
      }}
      transition={{
        duration: 2,
        delay,
        repeat: Infinity,
        repeatDelay: 1,
        ease: "easeInOut",
      }}
    />
  )
}

function AnimatedPacketReverse({ delay }: { delay: number }) {
  return (
    <motion.circle
      cx="0"
      cy="0"
      r="3"
      fill="hsl(217, 91%, 60%)"
      initial={{ opacity: 0 }}
      animate={{
        opacity: [0, 1, 1, 0],
        cx: [260, 60],
        cy: [100, 100],
      }}
      transition={{
        duration: 2,
        delay,
        repeat: Infinity,
        repeatDelay: 1.5,
        ease: "easeInOut",
      }}
    />
  )
}

export function NetworkVisualizer() {
  return (
    <div className="flex items-center gap-4 rounded-xl border border-border/50 bg-card/30 px-4 py-3 backdrop-blur-sm">
      <svg
        viewBox="0 0 320 160"
        className="h-20 w-full max-w-md shrink-0"
        aria-label="Network diagram showing Edge GPU and Cloud GPU communication"
      >
        {/* Edge Node */}
        <rect x="10" y="50" width="100" height="60" rx="8" fill="hsl(240, 4%, 14%)" stroke="hsl(142, 71%, 45%)" strokeWidth="1.5" strokeOpacity="0.5" />
        <text x="60" y="75" textAnchor="middle" fill="hsl(142, 71%, 45%)" fontSize="10" fontWeight="600">Edge Draft</text>
        <text x="60" y="92" textAnchor="middle" fill="hsl(240, 5%, 55%)" fontSize="8">RTX 3060</text>

        {/* Cloud Node */}
        <rect x="210" y="50" width="100" height="60" rx="8" fill="hsl(240, 4%, 14%)" stroke="hsl(217, 91%, 60%)" strokeWidth="1.5" strokeOpacity="0.5" />
        <text x="260" y="75" textAnchor="middle" fill="hsl(217, 91%, 60%)" fontSize="10" fontWeight="600">Cloud Target</text>
        <text x="260" y="92" textAnchor="middle" fill="hsl(240, 5%, 55%)" fontSize="8">H100</text>

        {/* Dashed lines */}
        <line x1="110" y1="75" x2="210" y2="75" stroke="hsl(142, 71%, 45%)" strokeWidth="1" strokeDasharray="4 4" strokeOpacity="0.3" />
        <line x1="110" y1="95" x2="210" y2="95" stroke="hsl(217, 91%, 60%)" strokeWidth="1" strokeDasharray="4 4" strokeOpacity="0.3" />

        {/* Labels */}
        <text x="160" y="70" textAnchor="middle" fill="hsl(240, 5%, 55%)" fontSize="7">Draft Tokens</text>
        <text x="160" y="108" textAnchor="middle" fill="hsl(240, 5%, 55%)" fontSize="7">Verified Tokens</text>

        {/* Arrow heads */}
        <polygon points="205,72 210,75 205,78" fill="hsl(142, 71%, 45%)" fillOpacity="0.5" />
        <polygon points="115,92 110,95 115,98" fill="hsl(217, 91%, 60%)" fillOpacity="0.5" />

        {/* Animated packets */}
        <AnimatedPacket delay={0} />
        <AnimatedPacket delay={1.2} />
        <AnimatedPacketReverse delay={0.5} />
        <AnimatedPacketReverse delay={1.8} />
      </svg>

      <div className="flex shrink-0 flex-col gap-2 text-xs text-muted-foreground">
        <div className="flex items-center gap-1.5">
          <Cpu className="h-3.5 w-3.5 text-green-400" />
          <span>Edge Node</span>
        </div>
        <div className="flex items-center gap-1.5">
          <Server className="h-3.5 w-3.5 text-blue-400" />
          <span>Cloud Node</span>
        </div>
      </div>
    </div>
  )
}
