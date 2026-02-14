"use client"

import { motion } from "framer-motion"
import { Card, CardContent } from "@/components/ui/card"
import { DollarSign, TrendingUp } from "lucide-react"

export function TotalEarningsCard() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1, duration: 0.4 }}
    >
      <Card className="border-border/50 bg-card/50 backdrop-blur-sm">
        <CardContent className="p-6">
          <div className="flex items-start">
            <div>
              <div className="flex items-center gap-2">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 ring-1 ring-primary/20">
                  <DollarSign className="h-4 w-4 text-primary" />
                </div>
                <p className="font-heading text-sm font-medium text-muted-foreground">
                  Total Earnings this Month
                </p>
              </div>
              <div className="mt-4 flex items-baseline gap-3">
                <span className="font-heading text-5xl font-bold tracking-tight text-foreground">
                  $42.50
                </span>
                <span className="flex items-center gap-1 rounded-md bg-primary/10 px-2 py-0.5 text-xs font-semibold text-primary">
                  <TrendingUp className="h-3 w-3" />
                  +12% vs last week
                </span>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  )
}
