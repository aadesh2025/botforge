import { beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { DeleteKnowledgeBase } from "./delete-kb";
import { useSession } from "@/lib/store/session";
import type { ApiAttachedAgent } from "@/lib/api/types";

const deleteKnowledgeBase = vi.fn();
vi.mock("@/lib/api/knowledge", () => ({
  deleteKnowledgeBase: (id: string) => deleteKnowledgeBase(id),
}));

const can = vi.fn();
vi.mock("@/lib/rbac", () => ({ useCan: (p: string) => can(p) }));

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

function renderIt(attached: ApiAttachedAgent[] = [], documentCount = 3) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <DeleteKnowledgeBase
        kbId="kb-1"
        name="Product Docs"
        documentCount={documentCount}
        attachedAgents={attached}
      />
    </QueryClientProvider>,
  );
}

const openDialog = () =>
  fireEvent.click(screen.getByRole("button", { name: /delete knowledge base/i }));

beforeEach(() => {
  vi.clearAllMocks();
  useSession.setState({ activeOrgId: "org-1" });
  can.mockReturnValue(true);
  deleteKnowledgeBase.mockResolvedValue(undefined);
});

describe("DeleteKnowledgeBase", () => {
  it("deletes and returns to the list once confirmed", async () => {
    renderIt();
    openDialog();
    fireEvent.click(await screen.findByRole("button", { name: /ok, delete it/i }));

    await vi.waitFor(() => expect(deleteKnowledgeBase).toHaveBeenCalledWith("kb-1"));
    await vi.waitFor(() => expect(push).toHaveBeenCalledWith("/knowledge"));
  });

  it("does not delete on the first click", async () => {
    // The endpoint is destructive and irreversible; the button opens a dialog, nothing more.
    renderIt();
    openDialog();
    await screen.findByRole("button", { name: /ok, delete it/i });
    expect(deleteKnowledgeBase).not.toHaveBeenCalled();
  });

  it("names the agents that will be left without grounding", async () => {
    // The whole point of the warning: a deleted KB doesn't break an agent, it silently stops
    // grounding it, and an ungrounded agent invents specifics.
    renderIt([
      { id: "a1", name: "Support Bot", is_live: true },
      { id: "a2", name: "Draft Bot", is_live: false },
    ]);
    openDialog();

    await screen.findByText("Support Bot");
    expect(screen.getByText("Draft Bot")).toBeInTheDocument();
    expect(screen.getByText(/answers may be invented/i)).toBeInTheDocument();
  });

  it("says nothing about agents when none use it", async () => {
    renderIt([]);
    openDialog();
    await screen.findByRole("button", { name: /ok, delete it/i });
    expect(screen.queryByText(/answers may be invented/i)).toBeNull();
  });

  it("surfaces a failure rather than pretending it worked", async () => {
    deleteKnowledgeBase.mockRejectedValue(new Error("Knowledge base not found."));
    renderIt();
    openDialog();
    fireEvent.click(await screen.findByRole("button", { name: /ok, delete it/i }));

    await screen.findByRole("alert");
    expect(push).not.toHaveBeenCalled();
  });

  it("is hidden from a role that cannot manage knowledge", () => {
    can.mockReturnValue(false);
    renderIt();
    expect(screen.queryByRole("button", { name: /delete knowledge base/i })).toBeNull();
  });
});
