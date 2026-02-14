"use client"

import { SendHorizonal } from "lucide-react"

export function ChatInput() {
  return (
    <div className="flex items-center gap-2 rounded-xl border border-border/50 bg-card/50 p-2 backdrop-blur-sm">
      <input
        type="text"
        placeholder="Ask SpecNet anything..."
        className="flex-1 bg-transparent px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
        aria-label="Chat message input"
      />
      <button
        type="button"
        className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground transition-colors hover:bg-primary/90"
        aria-label="Send message"
      >
        <SendHorizonal className="h-4 w-4" />
      </button>
    </div>
  )
}
