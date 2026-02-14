import { DashboardHeader } from "@/components/dashboard-header"
import { ProviderDashboard } from "@/components/provider-dashboard"

export const metadata = {
  title: "Provider Dashboard - SpecNet",
  description:
    "Track your Draft Node earnings, acceptance rate, and recent payouts on the SpecNet network.",
}

export default function ProviderPage() {
  return (
    <main className="flex h-screen flex-col overflow-hidden bg-background">
      <DashboardHeader />
      <ProviderDashboard />
    </main>
  )
}
