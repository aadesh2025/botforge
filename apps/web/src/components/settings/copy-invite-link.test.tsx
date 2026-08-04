import { beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { CopyInviteLink } from "./copy-invite-link";

const createInvitationLink = vi.fn();
vi.mock("@/lib/api/orgs", () => ({
  createInvitationLink: (...a: unknown[]) => createInvitationLink(...a),
}));

const writeText = vi.fn();

function renderIt() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <CopyInviteLink orgId="org-1" invitationId="inv-1" email="client@acme.com" />
    </QueryClientProvider>,
  );
}

const open = () => fireEvent.click(screen.getByRole("button", { name: /copy invite link for/i }));

beforeEach(() => {
  vi.clearAllMocks();
  writeText.mockResolvedValue(undefined);
  Object.assign(navigator, { clipboard: { writeText } });
  createInvitationLink.mockResolvedValue({
    accept_url: "http://localhost:3001/invitations/accept?token=abc123",
    expires_at: new Date().toISOString(),
  });
});

describe("CopyInviteLink", () => {
  it("warns that generating replaces the emailed link, before generating anything", async () => {
    // Minting is destructive — the old token stops working — so it must not happen on open.
    renderIt();
    open();

    await screen.findByText(/replaces any link already/i);
    expect(createInvitationLink).not.toHaveBeenCalled();
  });

  it("generates and copies once confirmed", async () => {
    renderIt();
    open();
    fireEvent.click(await screen.findByRole("button", { name: /generate & copy link/i }));

    await screen.findByText(/copied to clipboard/i);
    expect(createInvitationLink).toHaveBeenCalledWith("org-1", "inv-1");
    expect(writeText).toHaveBeenCalledWith("http://localhost:3001/invitations/accept?token=abc123");
  });

  it("still shows the link when the clipboard is unavailable", async () => {
    // Clipboard access needs a secure context and can be denied; losing the copy must not lose
    // the link, which is the only way in when email delivery is off.
    writeText.mockRejectedValue(new Error("denied"));
    renderIt();
    open();
    fireEvent.click(await screen.findByRole("button", { name: /generate & copy link/i }));

    const field = await screen.findByDisplayValue(
      "http://localhost:3001/invitations/accept?token=abc123",
    );
    expect(field).toBeInTheDocument();
    expect(screen.getByText(/select the link above/i)).toBeInTheDocument();
  });

  it("surfaces a failure instead of pretending it copied", async () => {
    createInvitationLink.mockRejectedValue(new Error("That invitation is no longer pending."));
    renderIt();
    open();
    fireEvent.click(await screen.findByRole("button", { name: /generate & copy link/i }));

    await screen.findByText(/no longer pending/i);
  });
});
