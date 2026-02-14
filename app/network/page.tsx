import { DashboardHeader } from "@/components/dashboard-header"
import { NetworkExplorer } from "@/components/network-explorer"

export const metadata = {
  title: "Network Explorer - SpecNet",
  description: "Live view of available Draft and Target nodes on the SpecNet distributed inference network.",
}

export default function NetworkPage() {
  return (
    <main className="flex h-screen flex-col overflow-hidden bg-background">
      <DashboardHeader />
      <NetworkExplorer />
    </main>
  )
}
