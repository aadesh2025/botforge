import { beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { AgentsPanel } from "./agents-panel";
import { useSession } from "@/lib/store/session";
import type { ApiAgent } from "@/lib/api/types";

const listAgents = vi.fn();
vi.mock("@/lib/api/agents", () => ({ listAgents: () => listAgents() }));

function agent(over: Partial<ApiAgent> & { id: string; name: string }): ApiAgent {
  return {
    slug: over.name.toLowerCase(),
    description: null,
    status: "draft",
    public_key: "pk_x",
    is_public: false,
    current_version_id: null,
    draft_version: 1,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...over,
  };
}

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AgentsPanel />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  useSession.setState({ activeOrgId: "org-1" });
});

describe("AgentsPanel", () => {
  it("prompts a brand-new org to create an agent instead of rendering nothing", async () => {
    listAgents.mockResolvedValue([]);
    renderPanel();
    expect(await screen.findByText("No agents yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Create your first agent/ })).toHaveAttribute(
      "href",
      "/agents",
    );
    expect(screen.getByText("0 total")).toBeInTheDocument();
  });

  it("never shows the retired mock agents to an org with none", async () => {
    // The bug this replaces: a zero-agent org saw four invented agents.
    listAgents.mockResolvedValue([]);
    renderPanel();
    await screen.findByText("No agents yet");
    for (const fake of ["Support Concierge", "Sales Qualifier", "Docs Assistant", "Order Tracker"]) {
      expect(screen.queryByText(fake)).toBeNull();
    }
  });

  it("renders the org's real agents with their API status", async () => {
    listAgents.mockResolvedValue([
      agent({ id: "a1", name: "Billing Bot", status: "published", description: "Answers invoices" }),
      agent({ id: "a2", name: "Draft Bot", status: "draft" }),
    ]);
    renderPanel();
    expect(await screen.findByText("Billing Bot")).toBeInTheDocument();
    expect(screen.getByText("Answers invoices")).toBeInTheDocument();
    // `published` must read as "Live", not be passed through raw.
    expect(screen.getByText("Live")).toBeInTheDocument();
    expect(screen.getByText("Draft")).toBeInTheDocument();
    expect(screen.getByText("2 total")).toBeInTheDocument();
  });

  it("links each agent to its own builder", async () => {
    listAgents.mockResolvedValue([agent({ id: "a1", name: "Billing Bot" })]);
    renderPanel();
    const link = await screen.findByRole("link", { name: /Billing Bot/ });
    expect(link).toHaveAttribute("href", "/agents/a1");
  });

  it("shows a skeleton, not an empty state, while the query is in flight", () => {
    listAgents.mockReturnValue(new Promise(() => {})); // never settles
    const { container } = renderPanel();
    expect(screen.getByText("Loading…")).toBeInTheDocument();
    expect(screen.queryByText("No agents yet")).toBeNull();
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull();
  });

  it("does not query until an org is active", async () => {
    useSession.setState({ activeOrgId: null });
    renderPanel();
    await waitFor(() => expect(listAgents).not.toHaveBeenCalled());
  });
});
