"use client"

import { useState, useMemo } from "react"
import { motion } from "framer-motion"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Server, ChevronDown } from "lucide-react"

const TARGET_NODES = [
  { provider: "Lambda Cloud", gpu: "H100 SXM5", vram: "80 GB", price: 2.49, premium: true },
  { provider: "CoreWeave", gpu: "H100 SXM5", vram: "80 GB", price: 2.23, premium: true },
  { provider: "RunPod", gpu: "H100 PCIe", vram: "80 GB", price: 2.69, premium: true },
  { provider: "Vast.ai", gpu: "A100 SXM4", vram: "80 GB", price: 1.12, premium: false },
  { provider: "Lambda Cloud", gpu: "A100 SXM4", vram: "40 GB", price: 0.99, premium: false },
  { provider: "CoreWeave", gpu: "A10G", vram: "24 GB", price: 0.76, premium: false },
  { provider: "RunPod", gpu: "A100 PCIe", vram: "40 GB", price: 1.04, premium: false },
  { provider: "Vast.ai", gpu: "L40S", vram: "48 GB", price: 0.89, premium: false },
]

const GPU_TYPES = ["All GPUs", "H100 SXM5", "H100 PCIe", "A100 SXM4", "A100 PCIe", "A10G", "L40S"]

export function TargetNodesTable() {
  const [gpuFilter, setGpuFilter] = useState("All GPUs")

  const filtered = useMemo(
    () => (gpuFilter === "All GPUs" ? TARGET_NODES : TARGET_NODES.filter((n) => n.gpu === gpuFilter)),
    [gpuFilter]
  )

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3, duration: 0.5 }}>
      <Card className="border-border/50 bg-card/50 backdrop-blur-sm">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2 font-heading text-sm font-medium text-muted-foreground">
              <Server className="h-4 w-4 text-accent" />
              Target Nodes (Cloud)
            </CardTitle>
            <Badge variant="outline" className="border-accent/30 bg-accent/10 text-accent font-mono text-[10px]">
              {filtered.length} nodes
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="px-4 pb-4">
          {/* Filter bar */}
          <div className="mb-3 flex items-center gap-2">
            <div className="relative">
              <select
                value={gpuFilter}
                onChange={(e) => setGpuFilter(e.target.value)}
                className="appearance-none rounded-md border border-border/60 bg-secondary/50 py-1.5 pl-3 pr-8 text-xs text-foreground outline-none transition-colors hover:bg-secondary focus:ring-1 focus:ring-ring"
              >
                {GPU_TYPES.map((t) => (
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
                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">Provider</th>
                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">GPU Type</th>
                  <th className="hidden px-3 py-2 text-left font-medium text-muted-foreground sm:table-cell">VRAM</th>
                  <th className="px-3 py-2 text-right font-medium text-muted-foreground">Price/Hr</th>
                  <th className="px-3 py-2 text-right font-medium text-muted-foreground">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((node, i) => (
                  <tr
                    key={`${node.provider}-${node.gpu}-${i}`}
                    className={`border-b border-border/20 transition-colors hover:bg-secondary/20 ${
                      node.premium ? "bg-accent/[0.03]" : ""
                    }`}
                  >
                    <td className="px-3 py-2.5 text-foreground">{node.provider}</td>
                    <td className="px-3 py-2.5">
                      <span className="flex items-center gap-1.5">
                        <span className={`font-mono ${node.premium ? "text-accent font-semibold" : "text-foreground"}`}>
                          {node.gpu}
                        </span>
                        {node.premium && (
                          <Badge className="border-0 bg-accent/15 px-1.5 py-0 text-[9px] text-accent">
                            PRO
                          </Badge>
                        )}
                      </span>
                    </td>
                    <td className="hidden px-3 py-2.5 font-mono text-muted-foreground sm:table-cell">{node.vram}</td>
                    <td className="px-3 py-2.5 text-right font-mono text-foreground">
                      ${node.price.toFixed(2)}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      <button
                        className={`rounded-md px-3 py-1 text-[10px] font-semibold transition-colors ${
                          node.premium
                            ? "bg-accent text-accent-foreground hover:bg-accent/90"
                            : "bg-secondary text-secondary-foreground hover:bg-secondary/80"
                        }`}
                      >
                        Connect
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  )
}
