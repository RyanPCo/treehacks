"use client"

import { useState } from "react"
import { SendHorizonal } from "lucide-react"

interface ChatInputProps {
  onSubmit: (prompt: string) => void
  disabled?: boolean
}

export function ChatInput({ onSubmit, disabled }: ChatInputProps) {
  const [value, setValue] = useState("")

  const handleSubmit = () => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSubmit(trimmed)
    setValue("")
  }

  return (
    <div className="flex items-center gap-2 rounded-xl border border-border/50 bg-card/50 p-2 backdrop-blur-sm">
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault()
            handleSubmit()
          }
        }}
        placeholder="Ask SpecNet anything..."
        disabled={disabled}
        className="flex-1 bg-transparent px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none disabled:opacity-50"
        aria-label="Chat message input"
      />
      <button
        type="button"
        onClick={handleSubmit}
        disabled={disabled || !value.trim()}
        className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
        aria-label="Send message"
      >
        <SendHorizonal className="h-4 w-4" />
      </button>
    </div>
  )
}
