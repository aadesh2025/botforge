"use client";

import Link from "next/link";
import { PanelLeftClose, PanelLeft, Sparkles, X } from "lucide-react";
import { Logo, LogoMark } from "@/components/brand/logo";
import { SidebarNav } from "./sidebar-nav";
import { OrgSwitcher } from "./org-switcher";
import { Button } from "@/components/ui/button";
import { useUI } from "@/lib/store/ui";
import { cn } from "@/lib/utils";
import { activeOrg, useSession } from "@/lib/store/session";

export function Sidebar() {
  const { collapsed, toggleCollapsed, mobileOpen, setMobileOpen } = useUI();

  return (
    <>
      {/* Mobile scrim */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      <aside
        className={cn(
          // h-screen + sticky bounds the sidebar to the viewport so its <nav> (min-h-0) scrolls
          // internally and the header + footer (Scale plan, Collapse) always stay in view.
          "fixed inset-y-0 left-0 z-50 flex flex-col border-r border-border bg-surface/95 backdrop-blur transition-[width,transform] duration-200 lg:sticky lg:top-0 lg:h-screen lg:translate-x-0",
          collapsed ? "w-[68px]" : "w-[248px]",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div
          className={cn(
            "flex h-14 items-center gap-2 border-b border-border px-4",
            collapsed && "justify-center px-0",
          )}
        >
          <Link href="/dashboard" className="flex items-center">
            {collapsed ? <LogoMark /> : <Logo />}
          </Link>
          {/* Primary collapse toggle — always beside the brand mark, never scroll-dependent.
              Shown on desktop only (mobile uses the ✕ below to close the drawer). */}
          <button
            className={cn(
              "rounded-md p-1 text-faint transition-colors hover:bg-surface-2 hover:text-text",
              collapsed ? "hidden lg:block" : "ml-auto hidden lg:block",
            )}
            onClick={toggleCollapsed}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? <PanelLeft className="size-[18px]" /> : <PanelLeftClose className="size-[18px]" />}
          </button>
          <button
            className="ml-auto rounded-md p-1 text-faint hover:text-text lg:hidden"
            onClick={() => setMobileOpen(false)}
            aria-label="Close navigation"
          >
            <X className="size-5" />
          </button>
        </div>

        <div className={cn("px-3 pt-3", collapsed && "px-2")}>
          <OrgSwitcher collapsed={collapsed} />
        </div>

        <SidebarNav collapsed={collapsed} />

        {/* Upgrade nudge + collapse control */}
        <div className={cn("border-t border-border p-3", collapsed && "px-2")}>
          {!collapsed && <PlanCard />}
          <Button
            variant="ghost"
            size={collapsed ? "icon" : "sm"}
            onClick={toggleCollapsed}
            className={cn("hidden w-full lg:flex", !collapsed && "justify-start")}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? <PanelLeft className="size-[18px]" /> : <PanelLeftClose className="size-[18px]" />}
            {!collapsed && <span>Collapse</span>}
          </Button>
        </div>
      </aside>
    </>
  );
}

/** The org's real plan.
 *
 * This card previously hardcoded "Scale plan" and "63% of monthly message credits used",
 * shown to every org regardless of plan — a Free-plan org saw Scale. There is no quota
 * endpoint, so no usage figure is displayed rather than an invented one. */
function PlanCard() {
  const org = useSession(activeOrg);
  if (!org) return null;
  const plan = org.plan.charAt(0).toUpperCase() + org.plan.slice(1);

  return (
    <div className="mb-3 overflow-hidden rounded-lg border border-accent/20 bg-accent/[0.06] p-3">
      <div className="flex items-center gap-2 text-sm font-medium text-text">
        <Sparkles className="size-4 text-accent-soft" /> {plan} plan
      </div>
      <p className="mt-1 text-xs text-muted">
        {org.plan === "free"
          ? "Free tier — bring your own provider keys for unlimited use."
          : `${org.name} is on the ${plan} plan.`}
      </p>
    </div>
  );
}
