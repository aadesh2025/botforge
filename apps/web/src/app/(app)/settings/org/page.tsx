import { UserPlus } from "lucide-react";
import { Section } from "@/components/settings/section";
import { Field } from "@/components/builder/field";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { members, roleMeta } from "@/lib/mock/settings";

export default function OrgSettingsPage() {
  return (
    <div className="space-y-6">
      <Section title="Organization profile" description="How your workspace appears across BotForge.">
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Name">
            <Input defaultValue="AUROZEN AI" />
          </Field>
          <Field label="Slug" description="Used in URLs and the widget key.">
            <Input defaultValue="aurozen" className="font-mono" />
          </Field>
        </div>
        <div className="mt-5">
          <Button variant="primary" size="sm">
            Save changes
          </Button>
        </div>
      </Section>

      <Section
        title="Members"
        description={`${members.filter((m) => m.status === "active").length} active · ${members.filter((m) => m.status === "invited").length} invited`}
        action={
          <Button variant="outline" size="sm">
            <UserPlus /> Invite
          </Button>
        }
        noPad
      >
        <ul className="divide-y divide-border">
          {members.map((m) => {
            const role = roleMeta[m.role];
            return (
              <li key={m.id} className="flex items-center gap-3 px-5 py-3.5">
                <Avatar className="size-9 border border-border">
                  <AvatarFallback className={m.status === "invited" ? "" : "bg-gradient-to-br from-ember to-ember-2 text-[#0A0B0D]"}>
                    {m.initials}
                  </AvatarFallback>
                </Avatar>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium text-text">
                      {m.status === "invited" ? m.email : m.name}
                    </span>
                    {m.status === "invited" && <Badge variant="warn">Invited</Badge>}
                  </div>
                  {m.status !== "invited" && <span className="text-xs text-faint">{m.email}</span>}
                </div>
                <Badge variant={role.variant}>{role.label}</Badge>
              </li>
            );
          })}
        </ul>
      </Section>
    </div>
  );
}
