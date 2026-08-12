import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { BarList } from "./bar-list";

/**
 * React reports duplicate keys through console.error, not by throwing, so the
 * only way to pin this regression is to watch that channel.
 */
function captureReactErrors() {
  return vi.spyOn(console, "error").mockImplementation(() => {});
}

function duplicateKeyWarnings(spy: ReturnType<typeof captureReactErrors>) {
  return spy.mock.calls.filter((args) => args.some((a) => typeof a === "string" && a.includes("same key")));
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("BarList", () => {
  it("renders both rows when two items share a label", () => {
    // Two agents may legitimately be named the same thing; neither may be dropped.
    const spy = captureReactErrors();
    render(
      <BarList
        items={[
          { id: "agent-1", label: "Customer Support", value: 900 },
          { id: "agent-2", label: "Customer Support", value: 300 },
        ]}
      />,
    );

    expect(screen.getAllByText("Customer Support")).toHaveLength(2);
    expect(screen.getByText("900")).toBeInTheDocument();
    expect(screen.getByText("300")).toBeInTheDocument();
    expect(duplicateKeyWarnings(spy)).toHaveLength(0);
  });

  it("does not warn on duplicate labels even when no id is supplied", () => {
    const spy = captureReactErrors();
    render(
      <BarList
        items={[
          { label: "Customer Support", value: 5 },
          { label: "Customer Support", value: 7 },
        ]}
      />,
    );

    expect(screen.getAllByText("Customer Support")).toHaveLength(2);
    expect(duplicateKeyWarnings(spy)).toHaveLength(0);
  });

  it("sizes each bar against the largest value", () => {
    const { container } = render(
      <BarList
        items={[
          { id: "a", label: "Groq", value: 100 },
          { id: "b", label: "OpenAI", value: 25 },
        ]}
      />,
    );

    const widths = Array.from(container.querySelectorAll<HTMLElement>("[style*='width']")).map(
      (el) => el.style.width,
    );
    expect(widths).toEqual(["100%", "25%"]);
  });

  it("does not divide by zero when every value is zero", () => {
    const { container } = render(
      <BarList
        items={[
          { id: "a", label: "Groq", value: 0 },
          { id: "b", label: "OpenAI", value: 0 },
        ]}
      />,
    );

    const widths = Array.from(container.querySelectorAll<HTMLElement>("[style*='width']")).map(
      (el) => el.style.width,
    );
    expect(widths).toEqual(["0%", "0%"]);
  });

  it("formats values through the supplied formatter", () => {
    render(<BarList items={[{ id: "a", label: "Groq", value: 1500 }]} format={(n) => `${n} tok`} />);
    expect(screen.getByText("1500 tok")).toBeInTheDocument();
  });
});
