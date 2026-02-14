"use client"

import { useState, useMemo } from "react"
import { motion } from "framer-motion"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Cpu, ChevronDown } from "lucide-react"
import type { NodeInfo } from "@/lib/types"

const DEFAULT_DRAFT_NODES = [
  { id: "node_7x9b", hardware: "RTX 3060", latency: 45, price: 0.05 },
  { id: "node_a2f1", hardware: "RTX 3070", latency: 32, price: 0.07 },
  { id: "node_k4c8", hardware: "Mac M2", latency: 58, price: 0.04 },
  { id: "node_p1d3", hardware: "RTX 4060", latency: 28, price: 0.08 },
  { id: "node_r8v2", hardware: "Mac M1 Pro", latency: 62, price: 0.03 },
  { id: "node_m5e9", hardware: "RTX 3080", latency: 38, price: 0.06 },
  { id: "node_q3w7", hardware: "RTX 3060", latency: 51, price: 0.04 },
  { id: "node_t6y4", hardware: "Mac M3", latency: 40, price: 0.06 },
  { id: "node_j9u1", hardware: "RTX 4070", latency: 25, price: 0.09 },
  { id: "node_h2b5", hardware: "RX 7600", latency: 55, price: 0.03 },
]

const HARDWARE_TYPES = ["All Hardware", "RTX 3060", "RTX 3070", "RTX 3080", "RTX 4060", "RTX 4070", "Mac M1 Pro", "Mac M2", "Mac M3", "RX 7600"]
const LATENCY_OPTIONS = ["Any Latency", "< 30ms", "< 50ms", "< 75ms"]

interface DraftNodesTableProps {
  nodes?: NodeInfo[]
}

function PulsingDot() {
  return (
    <span className="relative flex h-2 w-2">
      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75" />
      <span className="relative inline-flex h-2 w-2 rounded-full bg-green-500" />
    </span>
  )
}

export function DraftNodesTable({ nodes: liveNodes }: DraftNodesTableProps) {
  const [hardwareFilter, setHardwareFilter] = useState("All Hardware")
  const [latencyFilter, setLatencyFilter] = useState("Any Latency")

  // Map live NodeInfo[] to the table format, or use defaults
  const DRAFT_NODES = useMemo(() => {
    if (!liveNodes) return DEFAULT_DRAFT_NODES
    return liveNodes.map(n => ({
      id: n.id,
      hardware: n.hardware,
      latency: n.latency,
      price: n.price,
    }))
  }, [liveNodes])

  const filtered = useMemo(() => {
    let nodes = DRAFT_NODES
    if (hardwareFilter !== "All Hardware") {
      nodes = nodes.filter((n) => n.hardware === hardwareFilter)
    }
    if (latencyFilter !== "Any Latency") {
      const max = parseInt(latencyFilter.replace(/[^0-9]/g, ""), 10)
      nodes = nodes.filter((n) => n.latency < max)
    }
    return nodes
  }, [hardwareFilter, latencyFilter, DRAFT_NODES])

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4, duration: 0.5 }}>
      <Card className="border-border/50 bg-card/50 backdrop-blur-sm">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2 font-heading text-sm font-medium text-muted-foreground">
              <Cpu className="h-4 w-4 text-primary" />
              Draft Nodes (Edge)
            </CardTitle>
            <Badge variant="outline" className="border-primary/30 bg-primary/10 text-primary font-mono text-[10px]">
              {filtered.length} nodes
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="px-4 pb-4">
          {/* Filter bar */}
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <div className="relative">
              <select
                value={hardwareFilter}
                onChange={(e) => setHardwareFilter(e.target.value)}
                className="appearance-none rounded-md border border-border/60 bg-secondary/50 py-1.5 pl-3 pr-8 text-xs text-foreground outline-none transition-colors hover:bg-secondary focus:ring-1 focus:ring-ring"
              >
                {HARDWARE_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
            </div>
            <div className="relative">
              <select
                value={latencyFilter}
                onChange={(e) => setLatencyFilter(e.target.value)}
                className="appearance-none rounded-md border border-border/60 bg-secondary/50 py-1.5 pl-3 pr-8 text-xs text-foreground outline-none transition-colors hover:bg-secondary focus:ring-1 focus:ring-ring"
              >
                {LATENCY_OPTIONS.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
            </div>
          </div>

          {/* Table */}
          <div className="overflow-hidden rounded-lg border border-border/40">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border/40 bg-secondary/30">
                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">Node ID</th>
                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">Hardware</th>
                  <th className="px-3 py-2 text-right font-medium text-muted-foreground">Latency</th>
                  <th className="px-3 py-2 text-right font-medium text-muted-foreground">Price/Hr</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((node) => (
                  <tr
                    key={node.id}
                    className="border-b border-border/20 transition-colors hover:bg-secondary/20"
                  >
                    <td className="px-3 py-2.5">
                      <span className="flex items-center gap-2">
                        <PulsingDot />
                        <span className="font-mono text-foreground">{node.id}</span>
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-foreground">{node.hardware}</td>
                    <td className="px-3 py-2.5 text-right">
                      <span
                        className={`font-mono ${
                          node.latency < 35
                            ? "text-primary"
                            : node.latency < 55
                              ? "text-yellow-400"
                              : "text-orange-400"
                        }`}
                      >
                        {node.latency}ms
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono text-foreground">
                      ${node.price.toFixed(2)}/hr
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-3 py-6 text-center text-muted-foreground">
                      No nodes match the selected filters.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  )
}
