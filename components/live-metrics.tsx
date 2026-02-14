"use client"

import { motion } from "framer-motion"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { CheckCircle2, Zap, Wallet } from "lucide-react"

const cardVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: 0.3 + i * 0.15, duration: 0.5, ease: "easeOut" as const },
  }),
}

interface LiveMetricsProps {
  acceptanceRate?: number  // 0-100
  totalInferenceTimeSavedMs?: number
  costSavingsDollars?: number
}

export function LiveMetrics({
  acceptanceRate = 82,
  totalInferenceTimeSavedMs = 320,
  costSavingsDollars = 0.42,
}: LiveMetricsProps) {
  const timeSavedBar = Math.min(100, Math.max(0, (totalInferenceTimeSavedMs / 1500) * 100))
  const costBar = Math.min(100, Math.max(0, (costSavingsDollars / 2) * 100))

  return (
    <div className="flex flex-col gap-3">
      <motion.div custom={0} initial="hidden" animate="visible" variants={cardVariants}>
        <Card className="border-border/50 bg-card/50 backdrop-blur-sm">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 font-heading text-sm font-medium text-muted-foreground">
              <CheckCircle2 className="h-4 w-4 text-green-400" />
              Draft Acceptance Rate
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-baseline gap-2">
              <span className="font-heading text-3xl font-bold tracking-tight text-foreground">{Math.round(acceptanceRate)}%</span>
              <span className="text-xs text-muted-foreground">of draft tokens accepted</span>
            </div>
            <Progress value={acceptanceRate} className="mt-3 h-2" />
          </CardContent>
        </Card>
      </motion.div>

      <motion.div custom={1} initial="hidden" animate="visible" variants={cardVariants}>
        <Card className="border-border/50 bg-card/50 backdrop-blur-sm">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 font-heading text-sm font-medium text-muted-foreground">
              <Zap className="h-4 w-4 text-yellow-400" />
              Total Inference Time Saved
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-baseline gap-2">
              <span className="font-heading text-3xl font-bold tracking-tight text-foreground">
                {Math.round(totalInferenceTimeSavedMs)}ms
              </span>
              <span className="text-xs text-muted-foreground">saved vs baseline</span>
            </div>
            <div className="mt-3 flex items-center gap-1.5">
              <div className="h-1.5 flex-1 rounded-full bg-secondary">
                <div
                  className="h-full rounded-full bg-yellow-400/80 transition-all duration-500"
                  style={{ width: `${timeSavedBar}%` }}
                />
              </div>
              <span className="text-[10px] text-muted-foreground">vs 40 TPS baseline</span>
            </div>
          </CardContent>
        </Card>
      </motion.div>

      <motion.div custom={2} initial="hidden" animate="visible" variants={cardVariants}>
        <Card className="border-border/50 bg-card/50 backdrop-blur-sm">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 font-heading text-sm font-medium text-muted-foreground">
              <Wallet className="h-4 w-4 text-blue-400" />
              Cost Savings
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-baseline gap-2">
              <span className="font-heading text-3xl font-bold tracking-tight text-foreground">${costSavingsDollars.toFixed(2)}</span>
              <span className="text-xs text-muted-foreground">estimated saved this run</span>
            </div>
            <Progress value={costBar} className="mt-3 h-2 [&>[data-state]]:bg-blue-500" />
          </CardContent>
        </Card>
      </motion.div>
    </div>
  )
}
