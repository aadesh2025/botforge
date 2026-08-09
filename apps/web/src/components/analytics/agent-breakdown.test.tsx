import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { AgentBreakdown } from "./agent-breakdown";
import type { AgentBucket } from "@/lib/api/analytics";

function bucket(over: Partial<AgentBucket> = {}): AgentBucket {
  return {
    agent_id: "a1",
    name: "Support Bot",
    status: "published",
    deleted: false,
    conversations: 12,
    messages: 48,
    tokens_prompt: 9000,
    tokens_completion: 1200,
    cost_micros: 250_000,
    handoff_rate: 0.25,
    resolution_rate: 0.75,
    last_active_at: new Date().toISOString(),
    ...over,
  };
}

describe("AgentBreakdown", () => {
  it("renders a row per agent with its own traffic", () => {
    render(
      <AgentBreakdown
        buckets={[bucket(), bucket({ agent_id: "a2", name: "Sales Bot", conversations: 3 })]}
      />,
    );
    expect(screen.getByRole("row", { name: /Support Bot/ })).toBeInTheDocument();
    expect(screen.getByRole("row", { name: /Sales Bot/ })).toBeInTheDocument();
  });

  it("links each agent to its own analytics tab", () => {
    render(<AgentBreakdown buckets={[bucket()]} />);
    expect(screen.getByRole("link", { name: /Support Bot/ })).toHaveAttribute(
      "href",
      "/agents/a1?tab=analytics",
    );
  });

  it("keeps a silent agent visible and flags it", () => {
    // A published agent with no conversations usually means the embed was never installed —
    // the most useful thing this table can say. Filtering the row out hides it.
    render(<AgentBreakdown buckets={[bucket({ conversations: 0, messages: 0, last_active_at: null })]} />);
    const row = screen.getByRole("row", { name: /Support Bot/ });
    expect(within(row).getByText("no traffic")).toBeInTheDocument();
  });

  it("shows an em dash rather than 0% resolved for an agent with no conversations", () => {
    // 0% reads as "it failed to resolve anything" instead of "nothing happened yet".
    render(
      <AgentBreakdown
        buckets={[bucket({ conversations: 0, messages: 0, resolution_rate: 0, last_active_at: null })]}
      />,
    );
    const cells = screen.getAllByRole("cell").map((c) => c.textContent);
    expect(cells).toContain("—");
    expect(cells).not.toContain("0%");
  });

  it("shows a real resolution rate once there is traffic", () => {
    render(<AgentBreakdown buckets={[bucket({ conversations: 4, resolution_rate: 0.75 })]} />);
    expect(screen.getByText("75%")).toBeInTheDocument();
  });

  it("keeps a deleted agent's history but stops linking to a page that is gone", () => {
    // Measured against live data: an org's entire history can belong to a deleted agent, so
    // dropping the row makes the table stop summing to the headline number.
    render(<AgentBreakdown buckets={[bucket({ deleted: true, conversations: 9 })]} />);
    const row = screen.getByRole("row", { name: /Support Bot/ });
    expect(within(row).getByText("deleted")).toBeInTheDocument();
    expect(within(row).getByText("9")).toBeInTheDocument();
    expect(within(row).queryByRole("link")).not.toBeInTheDocument();
  });

  it("prompts a brand-new org instead of rendering an empty table", () => {
    render(<AgentBreakdown buckets={[]} />);
    expect(screen.getByText("No agents yet")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("shows a skeleton while loading rather than a false zero state", () => {
    const { container } = render(<AgentBreakdown buckets={undefined} isLoading />);
    expect(container.querySelector('[aria-busy="true"]')).toBeInTheDocument();
    expect(screen.queryByText("No agents yet")).not.toBeInTheDocument();
  });
});
