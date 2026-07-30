import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DeleteOrg } from "./delete-org";
import { useSession } from "@/lib/store/session";
import { deleteOrg, listOrgs } from "@/lib/api/orgs";
import { setActiveOrgId } from "@/lib/api/tokens";
import type { ApiOrg, ApiUser } from "@/lib/api/types";

const push = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }) }));
vi.mock("@/lib/api/orgs", () => ({ deleteOrg: vi.fn(), listOrgs: vi.fn() }));
vi.mock("@/lib/api/tokens", () => ({ setActiveOrgId: vi.fn() }));

function org(id: string, name: string, role: string): ApiOrg {
  return { id, name, slug: name.toLowerCase(), plan: "free", avatar_url: null, role } as ApiOrg;
}

function user(): ApiUser {
  return { id: "u1", email: "a@b.c", full_name: "A", is_staff: false } as ApiUser;
}

function renderWith(orgs: ApiOrg[]) {
  useSession.setState({ user: user(), orgs, activeOrgId: orgs[0]?.id ?? null, ready: true });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <DeleteOrg />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  useSession.setState({ user: null, orgs: [], activeOrgId: null, ready: false });
});

describe("DeleteOrg", () => {
  it("renders nothing for a role that can't manage the org", () => {
    // ORG_MANAGE is owner-only; an admin manages members but must not delete the workspace.
    const { container } = renderWith([org("o1", "Acme", "admin")]);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the danger zone to an owner", () => {
    renderWith([org("o1", "Acme", "owner")]);
    expect(screen.getByRole("button", { name: /delete organization/i })).toBeInTheDocument();
  });

  it("keeps the confirm button disabled until the exact name is typed", async () => {
    renderWith([org("o1", "Acme", "owner")]);
    fireEvent.click(screen.getByRole("button", { name: /delete organization/i }));

    const input = await screen.findByLabelText(/type acme to confirm/i);
    const confirm = screen.getAllByRole("button", { name: /delete organization/i }).at(-1)!;
    expect(confirm).toBeDisabled();

    // A near-miss must not arm it — this is the whole point of type-to-confirm.
    fireEvent.change(input, { target: { value: "acme" } });
    expect(confirm).toBeDisabled();

    fireEvent.change(input, { target: { value: "Acme" } });
    expect(confirm).toBeEnabled();
  });

  it("moves the session off the deleted org so later requests don't send a dead X-Org-Id", async () => {
    vi.mocked(deleteOrg).mockResolvedValue(undefined);
    vi.mocked(listOrgs).mockResolvedValue([org("o2", "Globex", "owner")]);

    renderWith([org("o1", "Acme", "owner"), org("o2", "Globex", "owner")]);
    fireEvent.click(screen.getByRole("button", { name: /delete organization/i }));
    fireEvent.change(await screen.findByLabelText(/type acme to confirm/i), {
      target: { value: "Acme" },
    });
    fireEvent.click(screen.getAllByRole("button", { name: /delete organization/i }).at(-1)!);

    await waitFor(() => expect(deleteOrg).toHaveBeenCalledWith("o1"));
    // The cookie is what X-Org-Id is built from; the store is what the UI renders. Both must move.
    await waitFor(() => expect(setActiveOrgId).toHaveBeenCalledWith("o2"));
    await waitFor(() => expect(useSession.getState().activeOrgId).toBe("o2"));
    expect(useSession.getState().orgs.map((o) => o.id)).toEqual(["o2"]);
    expect(push).toHaveBeenCalledWith("/dashboard");
  });

  it("survives deleting the last org without setting a bogus active org", async () => {
    vi.mocked(deleteOrg).mockResolvedValue(undefined);
    vi.mocked(listOrgs).mockResolvedValue([]);

    renderWith([org("o1", "Acme", "owner")]);
    fireEvent.click(screen.getByRole("button", { name: /delete organization/i }));
    fireEvent.change(await screen.findByLabelText(/type acme to confirm/i), {
      target: { value: "Acme" },
    });
    fireEvent.click(screen.getAllByRole("button", { name: /delete organization/i }).at(-1)!);

    await waitFor(() => expect(useSession.getState().orgs).toEqual([]));
    // Nothing to switch to — AuthGate's create-first-org prompt takes over.
    expect(setActiveOrgId).not.toHaveBeenCalled();
    expect(push).toHaveBeenCalledWith("/dashboard");
  });

  it("keeps the dialog open and shows why when the server refuses", async () => {
    vi.mocked(deleteOrg).mockRejectedValue(new Error("You do not have permission."));

    renderWith([org("o1", "Acme", "owner")]);
    fireEvent.click(screen.getByRole("button", { name: /delete organization/i }));
    fireEvent.change(await screen.findByLabelText(/type acme to confirm/i), {
      target: { value: "Acme" },
    });
    fireEvent.click(screen.getAllByRole("button", { name: /delete organization/i }).at(-1)!);

    expect(await screen.findByText(/do not have permission/i)).toBeInTheDocument();
    // The org list is untouched, so the UI still reflects reality.
    expect(useSession.getState().orgs.map((o) => o.id)).toEqual(["o1"]);
    expect(push).not.toHaveBeenCalled();
  });
});
