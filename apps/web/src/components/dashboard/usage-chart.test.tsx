import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { UsageChart } from "./usage-chart";
import type { DayPoint } from "@/lib/api/analytics";

function day(date: string, conversations: number, over: Partial<DayPoint> = {}): DayPoint {
  return {
    date,
    conversations,
    messages: conversations * 2,
    tokens_prompt: conversations * 100,
    tokens_completion: conversations * 20,
    cost_micros: 0,
    ...over,
  };
}

/** The path's vertical extent, used to tell a real curve from a flat line. */
function pathYs(d: string): number[] {
  return [...d.matchAll(/[-\d.]+,([-\d.]+)/g)].map((m) => Number(m[1]));
}

function linePath(container: HTMLElement): string {
  // The second <path> is the stroked line; the first is the gradient area fill.
  const paths = container.querySelectorAll("path");
  return paths[1]?.getAttribute("d") ?? "";
}

describe("UsageChart", () => {
  it("draws a curve, not a polyline, so varying days read as a shape", () => {
    const { container } = render(
      <UsageChart
        data={[day("2026-08-01", 1), day("2026-08-02", 9), day("2026-08-03", 2), day("2026-08-04", 7)]}
      />,
    );
    const d = linePath(container);
    expect(d).toContain("C"); // cubic segments
    expect(d).not.toMatch(/\sL/); // no straight line-to segments between points
  });

  it("never dips below the baseline on a spike, so counts can't render negative", () => {
    // A quiet stretch then a spike is exactly where a Catmull-Rom spline overshoots. Counts
    // have no negative values, so the curve must stay within the plot area.
    const { container } = render(
      <UsageChart
        data={[day("2026-08-01", 0), day("2026-08-02", 0), day("2026-08-03", 40), day("2026-08-04", 0)]}
      />,
    );
    const ys = pathYs(linePath(container));
    // y grows downward; the baseline is the bottom of the plot area (H - PAD.bottom = 214).
    expect(Math.max(...ys)).toBeLessThanOrEqual(214.5);
    expect(Math.min(...ys)).toBeGreaterThanOrEqual(0);
  });

  it("plots a point for every day given, including quiet ones", () => {
    // The straight-line bug: a sparse series plotted by index spaces scattered days evenly.
    // Gap-filling happens server-side, so the chart's contract is simply to honour it.
    const data = Array.from({ length: 14 }, (_, i) =>
      day(`2026-08-${String(i + 1).padStart(2, "0")}`, i === 0 || i === 13 ? 5 : 0),
    );
    const { container } = render(<UsageChart data={data} />);
    expect(container.querySelector("svg")).toHaveAttribute("aria-label", expect.stringContaining("14 days"));
  });

  it("labels the range from the data rather than a hardcoded window", () => {
    render(<UsageChart data={[day("2026-08-01", 1), day("2026-08-02", 2), day("2026-08-03", 3)]} />);
    // The header used to claim "Last 14 days" regardless of what was actually fetched.
    expect(screen.getByText(/Aug 1\s*–\s*Aug 3 · 3 days/)).toBeInTheDocument();
  });

  it("switches metric without losing the series", () => {
    const { container } = render(
      <UsageChart data={[day("2026-08-01", 1), day("2026-08-02", 4), day("2026-08-03", 2)]} />,
    );
    expect(screen.getByRole("button", { name: "conversations" })).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(screen.getByRole("button", { name: "tokens" }));
    expect(screen.getByRole("button", { name: "tokens" })).toHaveAttribute("aria-pressed", "true");
    expect(linePath(container)).toContain("C");
  });

  it("renders a flat baseline for an all-zero range instead of dividing by zero", () => {
    const { container } = render(
      <UsageChart data={[day("2026-08-01", 0), day("2026-08-02", 0), day("2026-08-03", 0)]} />,
    );
    const ys = pathYs(linePath(container));
    expect(ys.every((y) => Number.isFinite(y))).toBe(true);
    expect(new Set(ys.map((y) => y.toFixed(1))).size).toBe(1); // all on one line
  });

  it("says so when there is nothing at all", () => {
    render(<UsageChart data={[]} />);
    expect(screen.getByText("No usage in this period yet.")).toBeInTheDocument();
  });
});
