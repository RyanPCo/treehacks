"use client"

import { useRef, useCallback } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { ScrollArea } from "@/components/ui/scroll-area"
import { User, Bot } from "lucide-react"

export interface VisibleToken {
  text: string
  type: "accepted" | "rejected" | "corrected"
  phase: "appearing" | "striking" | "struck" | "hidden" | "settled"
}

interface ChatPanelProps {
  tokens: VisibleToken[]
  done: boolean
  counts: { accepted: number; rejected: number; corrected: number; drafted: number }
}

export function ChatPanel({ tokens, done, counts }: ChatPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null)

  const setRef = useCallback(
    (node: HTMLDivElement | null) => {
      if (node) {
        ;(scrollRef as React.MutableRefObject<HTMLDivElement | null>).current = node
        node.scrollTop = node.scrollHeight
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [tokens.length],
  )

  return (
    <div className="flex flex-1 flex-col overflow-hidden rounded-xl border border-border/50 bg-card/50 backdrop-blur-sm">
      {/* Chat header */}
      <div className="flex items-center justify-between border-b border-border/30 px-4 py-2.5">
        <span className="font-heading text-xs font-medium text-muted-foreground">
          Speculative Chat
        </span>
        <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-full bg-green-400" />
            Accepted
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-full bg-red-500" />
            Rejected
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-full bg-blue-400" />
            Corrected
          </span>
        </div>
      </div>

      {/* Messages */}
      <ScrollArea className="flex-1 p-4">
        <div className="flex flex-col gap-5" ref={setRef}>
          {/* User message */}
          <motion.div
            className="flex gap-3"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
          >
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-secondary">
              <User className="h-3.5 w-3.5 text-foreground" />
            </div>
            <div className="flex flex-col gap-1">
              <span className="font-heading text-[11px] font-medium text-muted-foreground">You</span>
              <p className="text-sm leading-relaxed text-foreground">
                Explain the theory of relativity.
              </p>
            </div>
          </motion.div>

          {/* AI response */}
          <motion.div
            className="flex gap-3"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.2 }}
          >
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary/10 ring-1 ring-primary/20">
              <Bot className="h-3.5 w-3.5 text-primary" />
            </div>
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <span className="font-heading text-[11px] font-medium text-muted-foreground">SpecNet</span>
              <div className="rounded-lg bg-secondary/40 p-3">
                <p className="font-mono text-sm leading-relaxed">
                  <AnimatePresence mode="popLayout">
                    {tokens.map((vt, i) => (
                      <TokenSpan key={`${i}-${vt.text}-${vt.type}`} token={vt} />
                    ))}
                  </AnimatePresence>
                  {!done && (
                    <span className="ml-0.5 inline-block h-4 w-[2px] animate-pulse bg-foreground align-middle" />
                  )}
                </p>
              </div>
              {/* Inline counters */}
              <div className="flex items-center gap-4 pt-1 text-[10px] tabular-nums text-muted-foreground">
                <span>{counts.drafted} drafted</span>
                <span className="text-green-400">{counts.accepted} accepted</span>
                <span className="text-red-500">{counts.rejected} rejected</span>
                <span className="text-blue-400">{counts.corrected} corrected</span>
              </div>
            </div>
          </motion.div>
        </div>
      </ScrollArea>
    </div>
  )
}

function TokenSpan({ token }: { token: VisibleToken }) {
  return (
    <motion.span
      className={tokenClass(token)}
      initial={{ opacity: 0, y: 3 }}
      animate={{ opacity: token.phase === "hidden" ? 0 : 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.8, transition: { duration: 0.12 } }}
      transition={{ duration: 0.15, ease: "easeOut" }}
      layout
    >
      {token.text}
    </motion.span>
  )
}

function tokenClass(token: VisibleToken): string {
  if (token.type === "accepted") return "text-green-400"
  if (token.type === "rejected") {
    if (token.phase === "appearing") return "text-red-400"
    if (token.phase === "striking" || token.phase === "struck")
      return "text-red-500 line-through opacity-50 transition-all duration-300"
    return "text-red-500 line-through opacity-0"
  }
  if (token.type === "corrected") {
    if (token.phase === "appearing") return "text-blue-400 font-semibold"
    return "text-blue-400 font-semibold"
  }
  return ""
}
