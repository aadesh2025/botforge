import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { TeamPerformance, formatDuration } from "./team-performance";
import type { AgentPerformanceBucket } from "@/lib/api/analytics";

function bucket(over: Partial<AgentPerformanceBucket> & { user_id: string; name: string }) {
  return {
    handoffs: 0,
    avg_first_response_ms: null,
    avg_resolution_ms: null,
    closed_count: 0,
    ...over,
  } as AgentPerformanceBucket;
}

describe("formatDuration", () => {
  it("scales the unit to the magnitude", () => {
    expect(formatDuration(450)).toBe("450ms");
    expect(formatDuration(4_500)).toBe("4.5s");
    expect(formatDuration(120_000)).toBe("2m");
    expect(formatDuration(5_400_000)).toBe("1.5h");
    expect(formatDuration(172_800_000)).toBe("2d");
  });

  it("shows a dash when there is nothing to average", () => {
    // A teammate who has never resolved anything hasn't achieved a 0ms resolution.
    expect(formatDuration(null)).toBe("—");
  });

  it("never produces NaN or undefined", () => {
    for (const out of [formatDuration(null), formatDuration(0), formatDuration(1)]) {
      expect(out).not.toContain("NaN");
      expect(out).not.toContain("undefined");
    }
  });
});

describe("TeamPerformance", () => {
  it("renders a row per teammate with their workload", () => {
    render(
      <TeamPerformance
        buckets={[
          bucket({
            user_id: "u1",
            name: "Aadesh",
            handoffs: 12,
            avg_first_response_ms: 45_000,
            avg_resolution_ms: 600_000,
            closed_count: 9,
          }),
        ]}
      />,
    );
    const row = screen.getByRole("row", { name: /Aadesh/ });
    expect(within(row).getByText("12")).toBeInTheDocument();
    expect(within(row).getByText("45.0s")).toBeInTheDocument();
    expect(within(row).getByText("10m")).toBeInTheDocument();
    expect(within(row).getByText("9")).toBeInTheDocument();
  });

  it("dashes the durations for someone who has taken over but not yet replied", () => {
    render(<TeamPerformance buckets={[bucket({ user_id: "u2", name: "Rohak", handoffs: 1 })]} />);
    const row = screen.getByRole("row", { name: /Rohak/ });
    expect(within(row).getAllByText("—")).toHaveLength(2);
  });

  it("prompts rather than rendering an empty table", () => {
    render(<TeamPerformance buckets={[]} />);
    expect(screen.getByText(/No handoffs have been taken over yet/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("tolerates undefined while the query is in flight", () => {
    render(<TeamPerformance buckets={undefined} isLoading />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });
});
