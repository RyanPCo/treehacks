"use client"

import { useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { NetworkVisualizer } from "@/components/network-visualizer"
import { LiveMetrics } from "@/components/live-metrics"
import { ChatStream } from "@/components/chat-stream"
import { ChatInput } from "@/components/chat-input"
import { PanelRightOpen, PanelRightClose } from "lucide-react"

export function DashboardBody() {
  const [sidebarOpen, setSidebarOpen] = useState(true)

  return (
    <div className="flex flex-1 gap-0 overflow-hidden">
      {/* Main content area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Network visualizer strip at the top */}
        <div className="shrink-0 border-b border-border/30 px-4 py-3">
          <NetworkVisualizer />
        </div>

        {/* Chat area fills remaining space */}
        <section className="flex flex-1 flex-col gap-3 overflow-hidden p-4">
          <ChatStream />
          <ChatInput />
        </section>
      </div>

      {/* Sidebar toggle button */}
      <div className="flex shrink-0 flex-col border-l border-border/30">
        <button
          type="button"
          onClick={() => setSidebarOpen(prev => !prev)}
          className="flex h-10 w-10 items-center justify-center text-muted-foreground transition-colors hover:bg-secondary/50 hover:text-foreground"
          aria-label={sidebarOpen ? "Close metrics sidebar" : "Open metrics sidebar"}
        >
          {sidebarOpen ? (
            <PanelRightClose className="h-4 w-4" />
          ) : (
            <PanelRightOpen className="h-4 w-4" />
          )}
        </button>
      </div>

      {/* Right sidebar: Metrics */}
      <AnimatePresence initial={false}>
        {sidebarOpen && (
          <motion.aside
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 320, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: "easeInOut" }}
            className="shrink-0 overflow-hidden border-l border-border/30"
          >
            <div className="flex h-full w-80 flex-col gap-3 overflow-y-auto p-4">
              <div className="flex items-center justify-between">
                <h3 className="font-heading text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Live Metrics
                </h3>
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-green-500" />
                </span>
              </div>
              <LiveMetrics />
            </div>
          </motion.aside>
        )}
      </AnimatePresence>
    </div>
  )
}
