import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { ChannelBreakdown, formatRate } from "./channel-breakdown";
import type { ChannelBucket } from "@/lib/api/analytics";

function bucket(over: Partial<ChannelBucket> & { channel: string }): ChannelBucket {
  return {
    conversations: 0,
    messages: 0,
    tokens_prompt: 0,
    tokens_completion: 0,
    cost_micros: 0,
    handoff_rate: 0,
    resolution_rate: 0,
    ...over,
  };
}

describe("formatRate", () => {
  it("renders a real rate as a percentage", () => {
    expect(formatRate(0.75, 4)).toBe("75%");
    expect(formatRate(1, 12)).toBe("100%");
  });

  it("shows a dash rather than 0% when nothing has happened yet", () => {
    // 0% resolution reads as failure; the channel simply has no traffic.
    expect(formatRate(0, 0)).toBe("—");
  });

  it("never produces NaN or undefined", () => {
    for (const out of [formatRate(0, 0), formatRate(0.5, 0), formatRate(0, 3)]) {
      expect(out).not.toContain("NaN");
      expect(out).not.toContain("undefined");
    }
  });
});

describe("ChannelBreakdown", () => {
  const rows = [
    bucket({ channel: "instagram", conversations: 8, messages: 30, cost_micros: 2_500_000, resolution_rate: 0.75 }),
    bucket({ channel: "whatsapp" }), // connected, no traffic yet
  ];

  it("renders a row per channel with a human label, not the raw key", () => {
    render(<ChannelBreakdown buckets={rows} />);
    expect(screen.getByRole("row", { name: /Instagram/ })).toBeInTheDocument();
    expect(screen.getByRole("row", { name: /WhatsApp/ })).toBeInTheDocument();
  });

  it("keeps a connected-but-empty channel visible as a real zero row", () => {
    render(<ChannelBreakdown buckets={rows} />);
    const row = screen.getByRole("row", { name: /WhatsApp/ });
    expect(within(row).getByText("no traffic")).toBeInTheDocument();
    expect(within(row).getByText("0")).toBeInTheDocument();
    expect(within(row).getByText("—")).toBeInTheDocument(); // not "0%"
  });

  it("shows the populated channel's real numbers", () => {
    render(<ChannelBreakdown buckets={rows} />);
    const row = screen.getByRole("row", { name: /Instagram/ });
    expect(within(row).getByText("8")).toBeInTheDocument();
    expect(within(row).getByText("75%")).toBeInTheDocument();
    expect(within(row).queryByText("no traffic")).toBeNull();
  });

  it("labels reporting-only channels instead of falling back to Other", () => {
    render(<ChannelBreakdown buckets={[bucket({ channel: "dashboard", conversations: 2 })]} />);
    expect(screen.getByRole("row", { name: /Dashboard/ })).toBeInTheDocument();
  });

  it("prompts rather than rendering an empty table when nothing is connected", () => {
    render(<ChannelBreakdown buckets={[]} />);
    expect(screen.getByText(/No channels connected yet/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("tolerates undefined while the query is in flight", () => {
    render(<ChannelBreakdown buckets={undefined} isLoading />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });
});
