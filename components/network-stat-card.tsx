"use client"

import { motion } from "framer-motion"
import { Card, CardContent } from "@/components/ui/card"
import type { LucideIcon } from "lucide-react"

interface NetworkStatCardProps {
  icon: LucideIcon
  label: string
  value: string
  sub: string
  color: string
  index: number
}

const cardVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.1, duration: 0.4, ease: "easeOut" as const },
  }),
}

export function NetworkStatCard({ icon: Icon, label, value, sub, color, index }: NetworkStatCardProps) {
  return (
    <motion.div custom={index} initial="hidden" animate="visible" variants={cardVariants}>
      <Card className="border-border/50 bg-card/50 backdrop-blur-sm">
        <CardContent className="p-5">
          <div className="flex items-center gap-3">
            <div
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg"
              style={{
                backgroundColor: `${color}15`,
                boxShadow: `inset 0 0 0 1px ${color}30`,
              }}
            >
              <Icon className="h-4 w-4" style={{ color }} />
            </div>
            <div className="min-w-0">
              <p className="text-xs text-muted-foreground">{label}</p>
              <div className="flex items-baseline gap-1.5">
                <span className="font-heading text-2xl font-bold tracking-tight text-foreground">{value}</span>
                <span className="text-xs text-muted-foreground">{sub}</span>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  )
}
