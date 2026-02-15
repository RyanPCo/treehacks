"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { Badge } from "@/components/ui/badge"
import { Network, Globe, Wallet, Play } from "lucide-react"

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: Network },
  { href: "/network", label: "Network Explorer", icon: Globe },
  { href: "/provider", label: "Provider Earnings", icon: Wallet },
  { href: "/visualize", label: "Visualize", icon: Play },
]

function Nav() {
  const pathname = usePathname()
  return (
    <nav className="hidden items-center gap-1 md:flex">
      {NAV_ITEMS.map((item) => {
        const active = pathname === item.href
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
              active
                ? "bg-secondary text-foreground"
                : "text-muted-foreground hover:bg-secondary/50 hover:text-foreground"
            }`}
          >
            <item.icon className="h-3.5 w-3.5" />
            {item.label}
          </Link>
        )
      })}
    </nav>
  )
}

export function DashboardHeader() {
  return (
    <header className="flex items-center justify-between border-b border-border/50 bg-card/30 px-6 py-4 backdrop-blur-sm">
      <div className="flex items-center gap-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 ring-1 ring-primary/20">
          <Network className="h-4 w-4 text-primary" />
        </div>
        <h1 className="font-heading text-lg font-bold tracking-tight text-foreground">SpecNet</h1>
        <span className="hidden text-xs text-muted-foreground sm:inline">
          Distributed Speculative Decoding
        </span>
      </div>
      <Nav />
      <Badge
        variant="outline"
        className="gap-1.5 border-green-500/30 bg-green-500/10 text-green-400"
      >
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-green-500" />
        </span>
        Network: Active
      </Badge>
    </header>
  )
}
