"use client";

import { Bell, Menu, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "./theme-toggle";
import { UserMenu } from "./user-menu";
import { useUI } from "@/lib/store/ui";

export function Topbar() {
  const setMobileOpen = useUI((s) => s.setMobileOpen);

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-bg/80 px-4 backdrop-blur-md md:px-6">
      <button
        className="rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-text lg:hidden"
        onClick={() => setMobileOpen(true)}
        aria-label="Open navigation"
      >
        <Menu className="size-5" />
      </button>

      {/* Command / search launcher */}
      <button className="group flex h-9 w-full max-w-sm items-center gap-2.5 rounded-md border border-border bg-surface px-3 text-sm text-faint transition-colors hover:border-border-strong hover:text-muted">
        <Search className="size-4" />
        <span className="flex-1 text-left">Search or jump to…</span>
        <kbd className="hidden items-center gap-0.5 rounded border border-border bg-surface-2 px-1.5 font-mono text-[11px] text-faint sm:inline-flex">
          ⌘K
        </kbd>
      </button>

      <div className="ml-auto flex items-center gap-1">
        <Button variant="ghost" size="icon" aria-label="Notifications" className="relative">
          <Bell className="size-[18px]" />
          <span className="absolute right-2 top-2 size-1.5 rounded-full bg-ember ring-2 ring-bg" />
        </Button>
        <ThemeToggle />
        <div className="mx-1.5 h-6 w-px bg-border" />
        <UserMenu />
      </div>
    </header>
  );
}
