"use client"

import { Badge } from "@/components/ui/badge"
import { Network } from "lucide-react"

export function DashboardHeader() {
  return (
    <header className="flex items-center justify-between border-b border-border/50 bg-card/30 px-6 py-4 backdrop-blur-sm">
      <div className="flex items-center gap-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 ring-1 ring-primary/20">
          <Network className="h-4 w-4 text-primary" />
        </div>
        <h1 className="text-lg font-bold tracking-tight text-foreground">SpecNet</h1>
        <span className="hidden text-xs text-muted-foreground sm:inline">
          Distributed Speculative Decoding
        </span>
      </div>
      <Badge
        variant="outline"
        className="gap-1.5 border-green-500/30 bg-green-500/10 text-green-400"
      >
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-green-500" />
        </span>
        Network: Active
      </Badge>
    </header>
  )
}
