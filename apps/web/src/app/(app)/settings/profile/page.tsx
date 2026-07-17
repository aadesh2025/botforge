import { Monitor, Smartphone } from "lucide-react";
import { Section } from "@/components/settings/section";
import { Field } from "@/components/builder/field";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { currentUser } from "@/lib/mock/data";

const sessions = [
  { id: "s1", device: "Chrome · Windows", location: "Coimbatore, IN", current: true, icon: Monitor },
  { id: "s2", device: "Safari · iPhone", location: "Coimbatore, IN", current: false, icon: Smartphone },
];

export default function ProfilePage() {
  return (
    <div className="space-y-6">
      <Section title="Profile" description="Your personal account details.">
        <div className="flex items-center gap-4">
          <Avatar className="size-14 border border-border">
            <AvatarFallback className="bg-gradient-to-br from-ember to-ember-2 text-lg text-[#0A0B0D]">
              {currentUser.initials}
            </AvatarFallback>
          </Avatar>
          <Button variant="outline" size="sm">
            Change avatar
          </Button>
        </div>
        <div className="mt-5 grid gap-5 sm:grid-cols-2">
          <Field label="Full name">
            <Input defaultValue={currentUser.name} />
          </Field>
          <Field label="Email">
            <Input defaultValue={currentUser.email} type="email" />
          </Field>
        </div>
        <div className="mt-5">
          <Button variant="primary" size="sm">
            Save changes
          </Button>
        </div>
      </Section>

      <Section title="Active sessions" description="Devices currently signed in to your account." noPad>
        <ul className="divide-y divide-border">
          {sessions.map((s) => (
            <li key={s.id} className="flex items-center gap-3 px-5 py-3.5">
              <span className="grid size-9 place-items-center rounded-md border border-border bg-surface-2 text-muted">
                <s.icon className="size-4" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-text">{s.device}</span>
                  {s.current && <Badge variant="success">This device</Badge>}
                </div>
                <span className="text-xs text-faint">{s.location}</span>
              </div>
              {!s.current && (
                <Button variant="ghost" size="sm" className="text-error hover:text-error">
                  Revoke
                </Button>
              )}
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}
