"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Check, ChevronsUpDown, Loader2, Plus } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { createOrg, listOrgs } from "@/lib/api/orgs";
import { setActiveOrgId } from "@/lib/api/tokens";
import { activeOrg, useSession } from "@/lib/store/session";
import { cn } from "@/lib/utils";

const planLabel: Record<string, string> = { free: "Free", pro: "Pro", scale: "Scale", enterprise: "Enterprise" };

export function OrgSwitcher({ collapsed }: { collapsed: boolean }) {
  const router = useRouter();
  const { orgs, activeOrgId, setOrgs, setActiveOrg } = useSession();
  const active = useSession(activeOrg);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  function switchOrg(id: string) {
    if (id === activeOrgId) return;
    setActiveOrgId(id);
    setActiveOrg(id);
    router.refresh();
  }

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await createOrg(name);
      const refreshed = await listOrgs();
      setOrgs(refreshed);
      const created = refreshed.find((o) => o.name === name);
      if (created) switchOrg(created.id);
      setCreating(false);
      setName("");
    } finally {
      setBusy(false);
    }
  }

  if (!active) return null;

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          className={cn(
            "flex w-full items-center gap-2.5 rounded-md border border-border bg-surface px-2.5 py-2 text-left transition-colors hover:border-border-strong hover:bg-surface-2",
            collapsed && "justify-center px-0",
          )}
        >
          <span className="grid size-7 shrink-0 place-items-center rounded-md bg-gradient-to-br from-ember to-ember-2 text-[13px] font-bold text-[#0A0B0D]">
            {active.name[0]?.toUpperCase()}
          </span>
          {!collapsed && (
            <>
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="truncate text-sm font-medium text-text">{active.name}</span>
                <span className="text-[11px] text-faint">{planLabel[active.plan] ?? active.plan} plan</span>
              </span>
              <ChevronsUpDown className="size-4 shrink-0 text-faint" />
            </>
          )}
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-[240px]">
          <DropdownMenuLabel>Organizations</DropdownMenuLabel>
          {orgs.map((org) => (
            <DropdownMenuItem key={org.id} onSelect={() => switchOrg(org.id)}>
              <span className="grid size-6 shrink-0 place-items-center rounded bg-surface-3 text-[11px] font-bold text-muted">
                {org.name[0]?.toUpperCase()}
              </span>
              <span className="flex-1 truncate text-text">{org.name}</span>
              {org.id === active.id && <Check className="size-4 text-ember-soft" />}
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => setCreating(true)}>
            <Plus className="size-4" />
            <span>New organization</span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New organization</DialogTitle>
          </DialogHeader>
          <form onSubmit={onCreate} className="space-y-4">
            <Input autoFocus placeholder="Organization name" value={name} onChange={(e) => setName(e.target.value)} />
            <Button type="submit" variant="primary" className="w-full" disabled={busy || !name.trim()}>
              {busy && <Loader2 className="size-4 animate-spin" />} Create
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
