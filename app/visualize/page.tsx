import { DashboardHeader } from "@/components/dashboard-header"
import { SpeculativeVisualizer } from "@/components/speculative-visualizer"

export default function VisualizePage() {
  return (
    <main className="flex h-screen flex-col overflow-hidden bg-background">
      <DashboardHeader />
      <SpeculativeVisualizer />
    </main>
  )
}
