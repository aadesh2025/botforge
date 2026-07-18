"use client";

import { useLayoutEffect, useMemo, useRef, useState } from "react";
import type { UsagePoint } from "@/lib/mock/types";
import { compact, usd } from "@/lib/utils";

type Metric = "conversations" | "tokens" | "cost";

const metricMeta: Record<Metric, { label: string; format: (n: number) => string }> = {
  conversations: { label: "Conversations", format: (n) => compact(n) },
  tokens: { label: "Tokens", format: (n) => compact(n) },
  cost: { label: "Cost", format: (n) => usd(n) },
};

const H = 240;
const PAD = { top: 16, right: 12, bottom: 26, left: 12 };

export function UsageChart({ data }: { data: UsagePoint[] }) {
  const [metric, setMetric] = useState<Metric>("conversations");
  const wrapRef = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(720);
  const [hover, setHover] = useState<number | null>(null);

  useLayoutEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const { areaPath, linePath, points } = useMemo(() => {
    if (data.length === 0) return { areaPath: "", linePath: "", points: [] as { x: number; y: number; v: number }[] };
    const values = data.map((d) => d[metric]);
    const max = Math.max(...values, 1) * 1.15;
    const innerW = w - PAD.left - PAD.right;
    const innerH = H - PAD.top - PAD.bottom;
    const x = (i: number) => PAD.left + (innerW * i) / Math.max(1, data.length - 1);
    const y = (v: number) => PAD.top + innerH - (innerH * v) / max;
    const pts = values.map((v, i) => ({ x: x(i), y: y(v), v }));
    const line = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
    const area = `${line} L${pts[pts.length - 1].x.toFixed(1)},${PAD.top + innerH} L${pts[0].x.toFixed(1)},${PAD.top + innerH} Z`;
    return { areaPath: area, linePath: line, points: pts };
  }, [data, metric, w]);

  if (data.length === 0) {
    return (
      <div className="flex h-[220px] items-center justify-center rounded-lg border border-border bg-surface text-sm text-muted">
        No usage in this period yet.
      </div>
    );
  }

  const active = hover ?? points.length - 1;
  const activePoint = points[active];
  const activeDate = new Date(data[active].date);
  // Keep the tooltip inside the chart: clamp x, and flip below the point when it sits high.
  const tipX = Math.max(52, Math.min(w - 52, activePoint.x));
  const flipDown = activePoint.y < 64;
  const tipY = flipDown ? activePoint.y + 14 : activePoint.y - 10;

  return (
    <div className="rounded-lg border border-border bg-surface">
      <div className="flex flex-col gap-3 border-b border-border p-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h3 className="font-display text-base font-semibold text-text">Activity</h3>
          <p className="text-sm text-muted">Last 14 days across all agents</p>
        </div>
        <div className="flex rounded-md border border-border bg-surface-2 p-0.5">
          {(Object.keys(metricMeta) as Metric[]).map((m) => (
            <button
              key={m}
              onClick={() => setMetric(m)}
              className={
                "rounded px-3 py-1 text-xs font-medium capitalize transition-colors " +
                (metric === m ? "bg-surface-3 text-text shadow-sm" : "text-muted hover:text-text")
              }
            >
              {m}
            </button>
          ))}
        </div>
      </div>

      <div ref={wrapRef} className="relative px-2 pb-2 pt-4">
        <svg
          width={w}
          height={H}
          className="overflow-visible"
          onMouseLeave={() => setHover(null)}
          onMouseMove={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const relX = e.clientX - rect.left;
            const innerW = w - PAD.left - PAD.right;
            const i = Math.round(((relX - PAD.left) / innerW) * (data.length - 1));
            setHover(Math.max(0, Math.min(data.length - 1, i)));
          }}
        >
          <defs>
            <linearGradient id="usage-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="rgb(255 106 61)" stopOpacity="0.28" />
              <stop offset="100%" stopColor="rgb(255 106 61)" stopOpacity="0" />
            </linearGradient>
            <linearGradient id="usage-stroke" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#FF6A3D" />
              <stop offset="100%" stopColor="#FFB020" />
            </linearGradient>
          </defs>

          {/* horizontal gridlines */}
          {[0.25, 0.5, 0.75].map((t) => {
            const yy = PAD.top + (H - PAD.top - PAD.bottom) * t;
            return (
              <line
                key={t}
                x1={PAD.left}
                x2={w - PAD.right}
                y1={yy}
                y2={yy}
                stroke="rgb(36 40 50)"
                strokeDasharray="3 5"
              />
            );
          })}

          <path d={areaPath} fill="url(#usage-fill)" />
          <path d={linePath} fill="none" stroke="url(#usage-stroke)" strokeWidth={2} strokeLinecap="round" />

          {/* hover crosshair */}
          <line
            x1={activePoint.x}
            x2={activePoint.x}
            y1={PAD.top}
            y2={H - PAD.bottom}
            stroke="rgb(255 106 61)"
            strokeOpacity={0.35}
          />
          <circle cx={activePoint.x} cy={activePoint.y} r={4.5} fill="#FF6A3D" stroke="#0A0B0D" strokeWidth={2} />

          {/* x labels: first, mid, last */}
          {[0, Math.floor(data.length / 2), data.length - 1].map((i) => (
            <text
              key={i}
              x={points[i].x}
              y={H - 8}
              textAnchor={i === 0 ? "start" : i === data.length - 1 ? "end" : "middle"}
              className="fill-faint font-mono text-[10px]"
            >
              {new Date(data[i].date).toLocaleDateString("en", { month: "short", day: "numeric" })}
            </text>
          ))}
        </svg>

        {/* Tooltip */}
        <div
          className={
            "pointer-events-none absolute -translate-x-1/2 rounded-md border border-border bg-surface-2 px-2.5 py-1.5 shadow-pop transition-[left,top] duration-75 " +
            (flipDown ? "translate-y-0" : "-translate-y-full")
          }
          style={{ left: tipX, top: tipY }}
        >
          <div className="font-mono text-[11px] text-faint">
            {activeDate.toLocaleDateString("en", { month: "short", day: "numeric" })}
          </div>
          <div className="text-sm font-semibold text-text">
            {metricMeta[metric].format(activePoint.v)}{" "}
            <span className="text-xs font-normal text-muted">{metricMeta[metric].label.toLowerCase()}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
