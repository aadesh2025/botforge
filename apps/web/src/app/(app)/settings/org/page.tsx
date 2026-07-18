"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Trash2, UserPlus } from "lucide-react";
import { Section } from "@/components/settings/section";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  changeMemberRole,
  createInvitation,
  listInvitations,
  listMembers,
  removeMember,
  revokeInvitation,
} from "@/lib/api/orgs";
import { useSession, activeOrg } from "@/lib/store/session";
import { useCan } from "@/lib/rbac";

const ASSIGNABLE = ["admin", "editor", "viewer", "operator"];

export default function OrgSettingsPage() {
  const qc = useQueryClient();
  const org = useSession(activeOrg);
  const orgId = org?.id ?? "";
  const canManage = useCan("members:manage");
  const [inviteOpen, setInviteOpen] = useState(false);

  const { data: members } = useQuery({
    queryKey: ["members", orgId],
    queryFn: () => listMembers(orgId),
    enabled: Boolean(orgId),
  });
  const { data: invites } = useQuery({
    queryKey: ["invitations", orgId],
    queryFn: () => listInvitations(orgId),
    enabled: Boolean(orgId) && canManage,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["members", orgId] });
    qc.invalidateQueries({ queryKey: ["invitations", orgId] });
  };
  const changeRole = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: string }) => changeMemberRole(orgId, userId, role),
    onSuccess: invalidate,
  });
  const remove = useMutation({ mutationFn: (userId: string) => removeMember(orgId, userId), onSuccess: invalidate });
  const revoke = useMutation({ mutationFn: (id: string) => revokeInvitation(orgId, id), onSuccess: invalidate });

  return (
    <div className="space-y-6">
      <Section title="Organization profile" description="How your workspace appears across BotForge.">
        <div className="grid gap-5 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs text-muted">Name</label>
            <Input value={org?.name ?? ""} readOnly />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted">Slug</label>
            <Input value={org?.slug ?? ""} readOnly className="font-mono" />
          </div>
        </div>
        <p className="mt-3 text-xs text-faint">Your role in this workspace: <span className="text-text">{org?.role}</span></p>
      </Section>

      <Section
        title="Members"
        description={`${(members ?? []).length} member${(members ?? []).length === 1 ? "" : "s"}`}
        action={
          canManage ? (
            <Button variant="outline" size="sm" onClick={() => setInviteOpen(true)}>
              <UserPlus /> Invite
            </Button>
          ) : undefined
        }
        noPad
      >
        <ul className="divide-y divide-border">
          {(members ?? []).map((m) => (
            <li key={m.user_id} className="flex items-center gap-3 px-5 py-3.5">
              <Avatar className="size-9 border border-border">
                <AvatarFallback className="bg-gradient-to-br from-ember to-ember-2 text-[#0A0B0D]">
                  {(m.full_name || m.email)[0]?.toUpperCase()}
                </AvatarFallback>
              </Avatar>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium text-text">{m.full_name || m.email}</div>
                <span className="text-xs text-faint">{m.email}</span>
              </div>
              {canManage && m.role !== "owner" ? (
                <select
                  value={m.role}
                  onChange={(e) => changeRole.mutate({ userId: m.user_id, role: e.target.value })}
                  className="h-8 rounded-md border border-border bg-surface-2 px-2 text-xs text-text"
                >
                  {ASSIGNABLE.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              ) : (
                <Badge variant={m.role === "owner" ? "ember" : "default"}>{m.role}</Badge>
              )}
              {canManage && m.role !== "owner" && (
                <button
                  onClick={() => remove.mutate(m.user_id)}
                  className="rounded-md p-1.5 text-faint transition-colors hover:bg-surface-2 hover:text-error"
                  title="Remove member"
                >
                  <Trash2 className="size-4" />
                </button>
              )}
            </li>
          ))}
        </ul>
      </Section>

      {canManage && (invites ?? []).length > 0 && (
        <Section title="Pending invitations" description="Awaiting acceptance." noPad>
          <ul className="divide-y divide-border">
            {(invites ?? []).map((inv) => (
              <li key={inv.id} className="flex items-center gap-3 px-5 py-3">
                <div className="min-w-0 flex-1">
                  <span className="text-sm text-text">{inv.email}</span>
                </div>
                <Badge variant="warn">{inv.role}</Badge>
                <button
                  onClick={() => revoke.mutate(inv.id)}
                  className="rounded-md p-1.5 text-faint transition-colors hover:bg-surface-2 hover:text-error"
                  title="Revoke invitation"
                >
                  <Trash2 className="size-4" />
                </button>
              </li>
            ))}
          </ul>
        </Section>
      )}

      <InviteDialog open={inviteOpen} onOpenChange={setInviteOpen} orgId={orgId} onInvited={invalidate} />
    </div>
  );
}

function InviteDialog({
  open,
  onOpenChange,
  orgId,
  onInvited,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  orgId: string;
  onInvited: () => void;
}) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("editor");
  const invite = useMutation({
    mutationFn: () => createInvitation(orgId, email, role),
    onSuccess: () => {
      setEmail("");
      onOpenChange(false);
      onInvited();
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Invite a member</DialogTitle>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            invite.mutate();
          }}
          className="space-y-3"
        >
          <Input type="email" placeholder="teammate@company.com" value={email} onChange={(e) => setEmail(e.target.value)} />
          <select
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="h-9 w-full rounded-md border border-border bg-surface-2 px-2 text-sm text-text"
          >
            {ASSIGNABLE.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
          {invite.isError && <p className="text-sm text-error">{(invite.error as Error).message}</p>}
          <Button type="submit" variant="primary" className="w-full" disabled={invite.isPending || !email.trim()}>
            {invite.isPending && <Loader2 className="size-4 animate-spin" />} Send invite
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
