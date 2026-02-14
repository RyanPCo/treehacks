import { DashboardHeader } from "@/components/dashboard-header"
import { DashboardBody } from "@/components/dashboard-body"

export default function Home() {
  return (
    <main className="flex h-screen flex-col overflow-hidden bg-background">
      <DashboardHeader />
      <DashboardBody />
    </main>
  )
}
