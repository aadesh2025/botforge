"use client";

import { useLayoutEffect, useMemo, useRef, useState } from "react";
import type { DayPoint } from "@/lib/api/analytics";
import { Skeleton } from "@/components/ui/skeleton";
import { compact, usd } from "@/lib/utils";

type Metric = "conversations" | "messages" | "tokens" | "cost";

const metricMeta: Record<Metric, { label: string; value: (d: DayPoint) => number; format: (n: number) => string }> = {
  conversations: { label: "Conversations", value: (d) => d.conversations, format: (n) => compact(n) },
  messages: { label: "Messages", value: (d) => d.messages, format: (n) => compact(n) },
  tokens: { label: "Tokens", value: (d) => d.tokens_prompt + d.tokens_completion, format: (n) => compact(n) },
  cost: { label: "Cost", value: (d) => d.cost_micros / 1_000_000, format: (n) => usd(n) },
};

const H = 240;
const PAD = { top: 16, right: 12, bottom: 26, left: 12 };

/** Parse `YYYY-MM-DD` as a *local* date.
 *
 * `new Date("2026-08-09")` is parsed as UTC midnight, which renders as the 8th anywhere west
 * of Greenwich — so the chart's labels disagreed with the day the data belongs to.
 */
function parseDay(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, (m ?? 1) - 1, d ?? 1);
}

/**
 * Monotone cubic interpolation (Fritsch–Carlson).
 *
 * Deliberately not a plain Catmull-Rom: that overshoots around sharp changes, and every
 * series here is a non-negative count, so a spike after a quiet week would dip the curve
 * *below zero* and draw days with negative conversations. Monotone segments cannot overshoot
 * their endpoints, so the curve stays inside the data.
 */
function smoothPath(pts: { x: number; y: number }[]): string {
  if (pts.length === 0) return "";
  if (pts.length === 1) return `M${pts[0].x},${pts[0].y}`;
  if (pts.length === 2) return `M${pts[0].x},${pts[0].y} L${pts[1].x},${pts[1].y}`;

  const n = pts.length;
  const dx: number[] = [];
  const slope: number[] = [];
  for (let i = 0; i < n - 1; i++) {
    const h = pts[i + 1].x - pts[i].x;
    dx.push(h);
    slope.push(h === 0 ? 0 : (pts[i + 1].y - pts[i].y) / h);
  }

  // Tangents: average of neighbouring slopes, forced to 0 at every local extremum so the
  // curve flattens instead of bulging past the point.
  const m: number[] = new Array(n).fill(0);
  m[0] = slope[0];
  m[n - 1] = slope[n - 2];
  for (let i = 1; i < n - 1; i++) {
    m[i] = slope[i - 1] * slope[i] <= 0 ? 0 : (slope[i - 1] + slope[i]) / 2;
  }
  for (let i = 0; i < n - 1; i++) {
    if (slope[i] === 0) {
      m[i] = 0;
      m[i + 1] = 0;
      continue;
    }
    const a = m[i] / slope[i];
    const b = m[i + 1] / slope[i];
    const s = a * a + b * b;
    if (s > 9) {
      const t = (3 / Math.sqrt(s)) * slope[i];
      m[i] = t * a;
      m[i + 1] = t * b;
    }
  }

  let d = `M${pts[0].x.toFixed(1)},${pts[0].y.toFixed(1)}`;
  for (let i = 0; i < n - 1; i++) {
    const c1x = pts[i].x + dx[i] / 3;
    const c1y = pts[i].y + (m[i] * dx[i]) / 3;
    const c2x = pts[i + 1].x - dx[i] / 3;
    const c2y = pts[i + 1].y - (m[i + 1] * dx[i]) / 3;
    d += ` C${c1x.toFixed(1)},${c1y.toFixed(1)} ${c2x.toFixed(1)},${c2y.toFixed(1)} ${pts[i + 1].x.toFixed(1)},${pts[i + 1].y.toFixed(1)}`;
  }
  return d;
}

export interface UsageChartProps {
  data: DayPoint[] | undefined;
  isLoading?: boolean;
  title?: string;
  /** Overrides the range description under the title. */
  subtitle?: string;
}

export function UsageChart({ data, isLoading, title = "Activity", subtitle }: UsageChartProps) {
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

  // Memoised so the `?? []` fallback doesn't hand the geometry a fresh array identity on
  // every render, which would recompute the whole path on each mouse move.
  const points = useMemo(() => data ?? [], [data]);

  const { areaPath, linePath, coords, max } = useMemo(() => {
    if (points.length === 0) {
      return { areaPath: "", linePath: "", coords: [] as { x: number; y: number; v: number }[], max: 0 };
    }
    const values = points.map(metricMeta[metric].value);
    const peak = Math.max(...values);
    // Headroom above the peak so the line never touches the top edge. An all-zero series
    // has no scale of its own, so it gets a nominal 1 and draws flat along the baseline.
    const scale = (peak > 0 ? peak : 1) * 1.15;
    const innerW = w - PAD.left - PAD.right;
    const innerH = H - PAD.top - PAD.bottom;
    const x = (i: number) => PAD.left + (innerW * i) / Math.max(1, points.length - 1);
    const y = (v: number) => PAD.top + innerH - (innerH * v) / scale;
    const pts = values.map((v, i) => ({ x: x(i), y: y(v), v }));
    const line = smoothPath(pts);
    const base = PAD.top + innerH;
    const area = line
      ? `${line} L${pts[pts.length - 1].x.toFixed(1)},${base} L${pts[0].x.toFixed(1)},${base} Z`
      : "";
    return { areaPath: area, linePath: line, coords: pts, max: peak };
  }, [points, metric, w]);

  if (isLoading) {
    return <Skeleton className="h-[340px] rounded-lg" />;
  }

  if (points.length === 0) {
    return (
      <div className="flex h-[220px] items-center justify-center rounded-lg border border-border bg-surface text-sm text-muted">
        No usage in this period yet.
      </div>
    );
  }

  const active = hover ?? coords.length - 1;
  const activePoint = coords[active];
  const activeDate = parseDay(points[active].date);
  // Keep the tooltip inside the chart: clamp x, and flip below the point when it sits high.
  const tipX = Math.max(52, Math.min(w - 52, activePoint.x));
  const flipDown = activePoint.y < 64;
  const tipY = flipDown ? activePoint.y + 14 : activePoint.y - 10;

  const first = parseDay(points[0].date);
  const last = parseDay(points[points.length - 1].date);
  const fmt = (d: Date) => d.toLocaleDateString("en", { month: "short", day: "numeric" });
  const rangeLabel = subtitle ?? `${fmt(first)} – ${fmt(last)} · ${points.length} days`;

  // Label roughly every sixth day, always including the last, so a 30-day range doesn't
  // overprint its axis and a 7-day one still gets several marks.
  const step = Math.max(1, Math.ceil(points.length / 6));
  const tickIdx = [...new Set([...points.map((_, i) => i).filter((i) => i % step === 0), points.length - 1])];

  return (
    <div className="rounded-lg border border-border bg-surface">
      <div className="flex flex-col gap-3 border-b border-border p-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h3 className="font-display text-base font-semibold text-text">{title}</h3>
          <p className="text-sm text-muted">{rangeLabel}</p>
        </div>
        <div className="flex rounded-md border border-border bg-surface-2 p-0.5">
          {(Object.keys(metricMeta) as Metric[]).map((m) => (
            <button
              key={m}
              onClick={() => setMetric(m)}
              aria-pressed={metric === m}
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
          role="img"
          aria-label={`${metricMeta[metric].label} per day, ${rangeLabel}. Peak ${metricMeta[metric].format(max)}.`}
          onMouseLeave={() => setHover(null)}
          onMouseMove={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const relX = e.clientX - rect.left;
            const innerW = w - PAD.left - PAD.right;
            const i = Math.round(((relX - PAD.left) / innerW) * (points.length - 1));
            setHover(Math.max(0, Math.min(points.length - 1, i)));
          }}
        >
          <defs>
            <linearGradient id="usage-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" style={{ stopColor: "rgb(var(--accent))" }} stopOpacity="0.28" />
              <stop offset="100%" style={{ stopColor: "rgb(var(--accent))" }} stopOpacity="0" />
            </linearGradient>
            <linearGradient id="usage-stroke" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" style={{ stopColor: "rgb(var(--accent))" }} />
              <stop offset="100%" style={{ stopColor: "rgb(var(--glow))" }} />
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
                stroke="rgb(var(--border))"
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
            stroke="rgb(var(--accent))"
            strokeOpacity={0.35}
          />
          <circle cx={activePoint.x} cy={activePoint.y} r={4.5} className="fill-accent stroke-bg" strokeWidth={2} />

          {tickIdx.map((i) => (
            <text
              key={i}
              x={coords[i].x}
              y={H - 8}
              textAnchor={i === 0 ? "start" : i === points.length - 1 ? "end" : "middle"}
              className="fill-faint font-mono text-[10px]"
            >
              {fmt(parseDay(points[i].date))}
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
