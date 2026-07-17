import { SettingsNav } from "@/components/settings/settings-nav";

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-[1100px]">
      <div className="mb-6">
        <h1 className="font-display text-2xl font-semibold tracking-tight text-text">Settings</h1>
        <p className="text-sm text-muted">Manage your organization, keys, and account.</p>
      </div>
      <div className="grid gap-6 lg:grid-cols-[200px_1fr]">
        <aside className="lg:sticky lg:top-20 lg:h-fit">
          <SettingsNav />
        </aside>
        <div className="min-w-0">{children}</div>
      </div>
    </div>
  );
}
