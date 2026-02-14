"use client"

import { NetworkStatCard } from "@/components/network-stat-card"
import { TargetNodesTable } from "@/components/target-nodes-table"
import { DraftNodesTable } from "@/components/draft-nodes-table"
import { Activity, Zap, DollarSign } from "lucide-react"

const STATS = [
  {
    icon: Activity,
    label: "Total Active Nodes",
    value: "1,204",
    sub: "nodes online",
    color: "hsl(142, 71%, 45%)",
  },
  {
    icon: Zap,
    label: "Current Network TPS",
    value: "48,720",
    sub: "tokens/sec",
    color: "hsl(48, 96%, 53%)",
  },
  {
    icon: DollarSign,
    label: "Avg Cost / 1k Tokens",
    value: "$0.0004",
    sub: "per 1k tokens",
    color: "hsl(217, 91%, 60%)",
  },
]

export function NetworkExplorer() {
  return (
    <div className="flex flex-1 flex-col gap-6 overflow-y-auto p-6">
      {/* Page header */}
      <div>
        <h2 className="font-heading text-2xl font-bold tracking-tight text-foreground">Network Explorer</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Live view of available Draft and Target nodes.
        </p>
      </div>

      {/* Stats row */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {STATS.map((stat, i) => (
          <NetworkStatCard key={stat.label} {...stat} index={i} />
        ))}
      </div>

      {/* Two-column tables */}
      <div className="grid gap-4 xl:grid-cols-2">
        <TargetNodesTable />
        <DraftNodesTable />
      </div>
    </div>
  )
}
