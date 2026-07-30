import { beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { VersionsTab } from "./versions-tab";
import { useSession } from "@/lib/store/session";
import type { ApiVersion } from "@/lib/api/types";

const listVersions = vi.fn();
const publishVersion = vi.fn();
const rollbackVersion = vi.fn();
vi.mock("@/lib/api/agents", () => ({
  listVersions: () => listVersions(),
  publishVersion: (...a: unknown[]) => publishVersion(...a),
  rollbackVersion: (...a: unknown[]) => rollbackVersion(...a),
}));

const can = vi.fn();
vi.mock("@/lib/rbac", () => ({ useCan: (p: string) => can(p) }));

function version(over: Partial<ApiVersion> & { id: string; version: number }): ApiVersion {
  return {
    is_published: false,
    system_prompt: null,
    persona: {},
    welcome_message: null,
    fallback_message: null,
    suggested_prompts: [],
    model_config: {},
    rag_config: {},
    features: {},
    created_at: new Date().toISOString(),
    ...over,
  };
}

function renderTab(currentVersionId: string | null = null) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <VersionsTab agentId="a1" currentVersionId={currentVersionId} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  useSession.setState({ activeOrgId: "org-1" });
  can.mockReturnValue(true);
  publishVersion.mockResolvedValue({});
  rollbackVersion.mockResolvedValue({});
});

describe("VersionsTab", () => {
  it("lists the agent's real versions, newest first", async () => {
    listVersions.mockResolvedValue([
      version({ id: "v1", version: 1, is_published: true }),
      version({ id: "v2", version: 2 }),
    ]);
    renderTab("v1");
    await screen.findByText("v2");
    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("v2");
    expect(items[1]).toHaveTextContent("v1");
  });

  it("never shows the retired mock history", async () => {
    listVersions.mockResolvedValue([version({ id: "v1", version: 1 })]);
    renderTab();
    await screen.findByText("v1");
    expect(screen.queryByText(/Tightened refund policy wording/)).toBeNull();
    expect(screen.queryByText(/Added shipping KB \+ handoff/)).toBeNull();
  });

  it("marks the live version as Current using current_version_id, not the highest number", async () => {
    // After a rollback the live version is an older one — the numeric max would be wrong.
    listVersions.mockResolvedValue([
      version({ id: "v1", version: 1, is_published: true }),
      version({ id: "v2", version: 2, is_published: true }),
    ]);
    renderTab("v1");
    await screen.findByText("v1");
    const older = screen.getAllByRole("listitem").find((li) => li.textContent?.includes("v1"))!;
    expect(older).toHaveTextContent("Current");
  });

  it("publishes a draft through the real endpoint", async () => {
    listVersions.mockResolvedValue([version({ id: "v2", version: 2 })]);
    renderTab("v1");
    fireEvent.click(await screen.findByRole("button", { name: /Publish/ }));
    await waitFor(() => expect(publishVersion).toHaveBeenCalledWith("a1", 2));
  });

  it("rolls back to a published version that isn't current", async () => {
    listVersions.mockResolvedValue([
      version({ id: "v1", version: 1, is_published: true }),
      version({ id: "v2", version: 2, is_published: true }),
    ]);
    renderTab("v2");
    fireEvent.click(await screen.findByRole("button", { name: /Roll back/ }));
    await waitFor(() => expect(rollbackVersion).toHaveBeenCalledWith("a1", 1));
  });

  it("hides publish and rollback from a role without agents:publish", async () => {
    can.mockReturnValue(false);
    listVersions.mockResolvedValue([
      version({ id: "v1", version: 1, is_published: true }),
      version({ id: "v2", version: 2 }),
    ]);
    renderTab("v1");
    await screen.findByText("v2");
    expect(screen.queryByRole("button", { name: /Publish/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Roll back/ })).toBeNull();
  });

  it("explains an agent with no versions yet", async () => {
    listVersions.mockResolvedValue([]);
    renderTab();
    expect(await screen.findByText(/No versions yet/)).toBeInTheDocument();
  });

  it("shows a skeleton while loading", () => {
    listVersions.mockReturnValue(new Promise(() => {}));
    const { container } = renderTab();
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull();
    expect(screen.queryByText(/No versions yet/)).toBeNull();
  });
});
