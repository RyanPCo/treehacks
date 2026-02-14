"use client"

import { motion } from "framer-motion"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { CheckCircle2, Zap, CloudOff } from "lucide-react"

const cardVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: 0.3 + i * 0.15, duration: 0.5, ease: "easeOut" as const },
  }),
}

export function LiveMetrics() {
  return (
    <div className="flex flex-col gap-3">
      <motion.div custom={0} initial="hidden" animate="visible" variants={cardVariants}>
        <Card className="border-border/50 bg-card/50 backdrop-blur-sm">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <CheckCircle2 className="h-4 w-4 text-green-400" />
              Draft Acceptance Rate
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-baseline gap-2">
              <span className="text-3xl font-bold tracking-tight text-foreground">82%</span>
              <span className="text-xs text-muted-foreground">of draft tokens accepted</span>
            </div>
            <Progress value={82} className="mt-3 h-2" />
          </CardContent>
        </Card>
      </motion.div>

      <motion.div custom={1} initial="hidden" animate="visible" variants={cardVariants}>
        <Card className="border-border/50 bg-card/50 backdrop-blur-sm">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <Zap className="h-4 w-4 text-yellow-400" />
              Effective Speed
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-baseline gap-2">
              <span className="text-3xl font-bold tracking-tight text-foreground">145</span>
              <span className="text-xs text-muted-foreground">tokens / second</span>
            </div>
            <div className="mt-3 flex items-center gap-1.5">
              <div className="h-1.5 flex-1 rounded-full bg-secondary">
                <div className="h-full w-[72%] rounded-full bg-yellow-400/80" />
              </div>
              <span className="text-[10px] text-muted-foreground">vs 40 TPS baseline</span>
            </div>
          </CardContent>
        </Card>
      </motion.div>

      <motion.div custom={2} initial="hidden" animate="visible" variants={cardVariants}>
        <Card className="border-border/50 bg-card/50 backdrop-blur-sm">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <CloudOff className="h-4 w-4 text-blue-400" />
              Cloud Compute Saved
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-baseline gap-2">
              <span className="text-3xl font-bold tracking-tight text-foreground">60%</span>
              <span className="text-xs text-muted-foreground">reduction in cloud calls</span>
            </div>
            <Progress value={60} className="mt-3 h-2 [&>[data-state]]:bg-blue-500" />
          </CardContent>
        </Card>
      </motion.div>
    </div>
  )
}
