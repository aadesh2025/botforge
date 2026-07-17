"use client";

import { useState } from "react";
import { Check, ChevronsUpDown, Plus } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { organizations } from "@/lib/mock/data";
import { cn } from "@/lib/utils";

const planMeta: Record<string, string> = { free: "Free", pro: "Pro", scale: "Scale" };

export function OrgSwitcher({ collapsed }: { collapsed: boolean }) {
  const [activeId, setActiveId] = useState(organizations[0].id);
  const active = organizations.find((o) => o.id === activeId) ?? organizations[0];

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className={cn(
          "flex w-full items-center gap-2.5 rounded-md border border-border bg-surface px-2.5 py-2 text-left transition-colors hover:border-border-strong hover:bg-surface-2",
          collapsed && "justify-center px-0",
        )}
      >
        <span className="grid size-7 shrink-0 place-items-center rounded-md bg-gradient-to-br from-ember to-ember-2 text-[13px] font-bold text-[#0A0B0D]">
          {active.name[0]}
        </span>
        {!collapsed && (
          <>
            <span className="flex min-w-0 flex-1 flex-col">
              <span className="truncate text-sm font-medium text-text">{active.name}</span>
              <span className="text-[11px] text-faint">{planMeta[active.plan]} plan</span>
            </span>
            <ChevronsUpDown className="size-4 shrink-0 text-faint" />
          </>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-[240px]">
        <DropdownMenuLabel>Organizations</DropdownMenuLabel>
        {organizations.map((org) => (
          <DropdownMenuItem key={org.id} onSelect={() => setActiveId(org.id)}>
            <span className="grid size-6 shrink-0 place-items-center rounded bg-surface-3 text-[11px] font-bold text-muted">
              {org.name[0]}
            </span>
            <span className="flex-1 truncate text-text">{org.name}</span>
            {org.id === active.id && <Check className="size-4 text-ember-soft" />}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem>
          <Plus className="size-4" />
          <span>New organization</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
