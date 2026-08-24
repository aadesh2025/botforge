import { beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { WorkflowsTab } from "./workflows-tab";
import { useSession } from "@/lib/store/session";
import type { ApiWorkflow } from "@/lib/api/types";

const listWorkflows = vi.fn();
const createWorkflow = vi.fn();
vi.mock("@/lib/api/workflows", () => ({
  listWorkflows: (...a: unknown[]) => listWorkflows(...a),
  createWorkflow: (...a: unknown[]) => createWorkflow(...a),
}));

// The canvas itself pulls in @xyflow/react (ResizeObserver/SVG-heavy) — out of scope for a
// jsdom unit test, and exercised instead by the Playwright check. This file only covers the
// list/create screen the tab shows before a workflow is selected.
vi.mock("@/components/builder/workflow-canvas/workflow-canvas", () => ({
  WorkflowCanvas: ({ workflow }: { workflow: ApiWorkflow }) => <div>canvas:{workflow.name}</div>,
}));

const can = vi.fn();
vi.mock("@/lib/rbac", () => ({ useCan: (p: string) => can(p) }));

function workflow(over: Partial<ApiWorkflow> & { id: string; name: string }): ApiWorkflow {
  return {
    organization_id: "org-1",
    agent_id: "a1",
    description: null,
    current_version_id: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...over,
  };
}

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <WorkflowsTab agentId="a1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  useSession.setState({ activeOrgId: "org-1" });
  can.mockReturnValue(true);
});

describe("WorkflowsTab", () => {
  it("explains the empty state instead of rendering a blank list", async () => {
    listWorkflows.mockResolvedValue([]);
    renderTab();
    expect(await screen.findByText(/No workflows yet/)).toBeInTheDocument();
  });

  it("shows a skeleton while loading", () => {
    listWorkflows.mockReturnValue(new Promise(() => {}));
    const { container } = renderTab();
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull();
  });

  it("lists real workflows and flags which are unpublished", async () => {
    listWorkflows.mockResolvedValue([
      workflow({ id: "w1", name: "Refund flow", current_version_id: "v1" }),
      workflow({ id: "w2", name: "Draft flow", current_version_id: null }),
    ]);
    renderTab();
    await screen.findByText("Refund flow");
    expect(screen.getByText("Published")).toBeInTheDocument();
    expect(screen.getByText("Draft only")).toBeInTheDocument();
  });

  it("opens the canvas for a selected workflow", async () => {
    listWorkflows.mockResolvedValue([workflow({ id: "w1", name: "Refund flow" })]);
    renderTab();
    fireEvent.click(await screen.findByText("Refund flow"));
    expect(await screen.findByText("canvas:Refund flow")).toBeInTheDocument();
    // The back button returns to the list.
    fireEvent.click(screen.getByRole("button", { name: /All workflows/ }));
    await screen.findByText("Refund flow");
    expect(screen.queryByText("canvas:Refund flow")).toBeNull();
  });

  it("creates a workflow and opens it", async () => {
    listWorkflows.mockResolvedValue([]);
    createWorkflow.mockResolvedValue(workflow({ id: "w-new", name: "New one" }));
    renderTab();
    await screen.findByText(/No workflows yet/);

    fireEvent.click(screen.getByRole("button", { name: /New workflow/ }));
    fireEvent.change(await screen.findByPlaceholderText(/Refund approval/), {
      target: { value: "New one" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Create workflow/ }));

    await waitFor(() => expect(createWorkflow).toHaveBeenCalledWith("a1", "New one"));
    expect(await screen.findByText("canvas:New one")).toBeInTheDocument();
  });

  it("hides creation from a role without workflows:write", async () => {
    can.mockReturnValue(false);
    listWorkflows.mockResolvedValue([workflow({ id: "w1", name: "Refund flow" })]);
    renderTab();
    await screen.findByText("Refund flow");
    expect(screen.queryByRole("button", { name: /New workflow/ })).toBeNull();
  });
});
