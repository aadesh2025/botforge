export function Section({
  title,
  description,
  action,
  children,
  noPad,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  noPad?: boolean;
}) {
  return (
    <section className="rounded-lg border border-border bg-surface">
      <div className="flex items-center justify-between gap-4 border-b border-border p-5">
        <div>
          <h2 className="font-display text-base font-semibold text-text">{title}</h2>
          {description && <p className="mt-0.5 text-sm text-muted">{description}</p>}
        </div>
        {action}
      </div>
      <div className={noPad ? "" : "p-5"}>{children}</div>
    </section>
  );
}
