"use client"

import { motion } from "framer-motion"
import { Plus } from "lucide-react"

export function ProviderHeader() {
  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="flex items-center justify-between"
    >
      <div>
        <h2 className="text-xl font-bold tracking-tight text-foreground">
          Provider Dashboard
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Manage your Draft Node and track earnings.
        </p>
      </div>
      <button className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90">
        <Plus className="h-4 w-4" />
        Add New Node
      </button>
    </motion.div>
  )
}
