"use client"

import { ProviderHeader } from "@/components/provider-header"
import { TotalEarningsCard } from "@/components/total-earnings-card"
import { ConnectedHardwareCard } from "@/components/connected-hardware-card"
import { ActivityChart } from "@/components/activity-chart"
import { RecentPayoutsTable } from "@/components/recent-payouts-table"

export function ProviderDashboard() {
  return (
    <div className="flex flex-1 flex-col gap-6 overflow-y-auto p-6">
      <ProviderHeader />

      {/* Big Metric */}
      <TotalEarningsCard />

      {/* Two-column: Hardware + Chart */}
      <div className="grid gap-6 xl:grid-cols-2">
        <ConnectedHardwareCard />
        <ActivityChart />
      </div>

      {/* Payouts */}
      <RecentPayoutsTable />
    </div>
  )
}
