"use client"

import { NetworkVisualizer } from "@/components/network-visualizer"
import { LiveMetrics } from "@/components/live-metrics"
import { ChatStream } from "@/components/chat-stream"
import { ChatInput } from "@/components/chat-input"

export function DashboardBody() {
  return (
    <div className="flex flex-1 gap-4 overflow-hidden p-4">
      {/* Left Sidebar: Telemetry & Network */}
      <aside className="hidden w-80 shrink-0 flex-col gap-3 overflow-y-auto lg:flex">
        <NetworkVisualizer />
        <LiveMetrics />
      </aside>

      {/* Main Area: Chat Stream + Input */}
      <section className="flex flex-1 flex-col gap-3 overflow-hidden">
        <ChatStream />
        <ChatInput />
      </section>
    </div>
  )
}
