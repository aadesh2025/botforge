import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { AcceptInvitation } from "./accept-invitation";
import { ApiError } from "@/lib/api/client";

const previewInvitation = vi.fn();
const acceptInvitation = vi.fn();
const listOrgs = vi.fn();
vi.mock("@/lib/api/orgs", () => ({
  previewInvitation: (t: string) => previewInvitation(t),
  acceptInvitation: (t: string) => acceptInvitation(t),
  listOrgs: () => listOrgs(),
}));

const signup = vi.fn();
const login = vi.fn();
const me = vi.fn();
vi.mock("@/lib/api/auth", () => ({
  signup: (...a: unknown[]) => signup(...a),
  login: (...a: unknown[]) => login(...a),
  me: () => me(),
}));

const getAccessToken = vi.fn();
vi.mock("@/lib/api/tokens", () => ({
  getAccessToken: () => getAccessToken(),
  setActiveOrgId: vi.fn(),
  clearAuth: vi.fn(),
}));

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
  useSearchParams: () => new URLSearchParams("token=tok-1"),
}));

function preview(over: Partial<{ account_exists: boolean }> = {}) {
  return {
    organization_name: "Acme Ltd",
    role: "editor",
    email: "client@acme.com",
    account_exists: false,
    expires_at: new Date().toISOString(),
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  getAccessToken.mockReturnValue(null); // signed out — the invitee's usual state
  me.mockResolvedValue({ user: { id: "u1" } });
  listOrgs.mockResolvedValue([]);
  acceptInvitation.mockResolvedValue({ id: "org-1", name: "Acme Ltd" });
});

describe("AcceptInvitation", () => {
  it("names the org and role instead of leaving the invitee guessing", async () => {
    previewInvitation.mockResolvedValue(preview());
    render(<AcceptInvitation />);

    await screen.findByText("Acme Ltd");
    expect(screen.getByText("editor")).toBeInTheDocument();
  });

  it("opens in sign-in mode when the address already has an account", async () => {
    // The whole bug: defaulting to signup sent existing users into auth.email_taken.
    previewInvitation.mockResolvedValue(preview({ account_exists: true }));
    render(<AcceptInvitation />);

    await screen.findByRole("button", { name: /sign in & join/i });
    expect(screen.queryByRole("button", { name: /create account & join/i })).toBeNull();
  });

  it("opens in signup mode for someone genuinely new", async () => {
    previewInvitation.mockResolvedValue(preview({ account_exists: false }));
    render(<AcceptInvitation />);

    await screen.findByRole("button", { name: /create account & join/i });
  });

  it("locks the email to the invited address", async () => {
    // Anything else is rejected server-side with org.invite_email_mismatch, so editing it can
    // only produce that error.
    previewInvitation.mockResolvedValue(preview());
    render(<AcceptInvitation />);

    const field = (await screen.findByLabelText(/email/i)) as HTMLInputElement;
    expect(field.value).toBe("client@acme.com");
    expect(field).toHaveAttribute("readonly");
  });

  it("switches to sign-in rather than showing a raw 'already exists' error", async () => {
    // Covers the race where the account appears between preview and submit, and the case where
    // the preview request itself failed.
    previewInvitation.mockRejectedValue(new Error("offline"));
    signup.mockRejectedValue(new ApiError(409, "auth.email_taken", "An account with this email already exists."));
    render(<AcceptInvitation />);

    fireEvent.change(await screen.findByLabelText(/email/i), {
      target: { value: "client@acme.com" },
    });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "password123" } });
    fireEvent.click(screen.getByRole("button", { name: /create account & join/i }));

    await screen.findByText(/you already have an account/i);
    expect(screen.queryByText(/an account with this email already exists/i)).toBeNull();
    expect(screen.getByRole("button", { name: /sign in & join/i })).toBeInTheDocument();
  });

  it("signs an existing user in and joins them to the org in one step", async () => {
    previewInvitation.mockResolvedValue(preview({ account_exists: true }));
    login.mockResolvedValue({});
    render(<AcceptInvitation />);

    fireEvent.change(await screen.findByLabelText(/password/i), {
      target: { value: "their-own-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in & join/i }));

    await vi.waitFor(() => expect(acceptInvitation).toHaveBeenCalledWith("tok-1"));
    expect(login).toHaveBeenCalledWith("client@acme.com", "their-own-password");
  });
});
