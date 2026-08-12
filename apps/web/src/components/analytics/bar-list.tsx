import { compact } from "@/lib/utils";

export function BarList({
  items,
  format = (n) => compact(n),
}: {
  /**
   * `label` is display text and is NOT unique — two agents may share a name, and
   * two channel keys may map to one label. Pass `id` wherever the source row has
   * a stable identifier; it is what keys the row.
   */
  items: { id?: string; label: string; value: number }[];
  format?: (n: number) => string;
}) {
  const max = Math.max(...items.map((i) => i.value), 1);
  return (
    <div className="space-y-3">
      {items.map((item, i) => (
        <div key={item.id ?? `${item.label}:${i}`} className="space-y-1.5">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted">{item.label}</span>
            <span className="font-mono text-xs text-text">{format(item.value)}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-surface-3">
            <div
              className="h-full rounded-full bg-gradient-to-r from-accent to-accent-2"
              style={{ width: `${(item.value / max) * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
