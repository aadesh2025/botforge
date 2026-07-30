import { expect, test } from "@playwright/test";
import { API, WEB, uniqueEmail } from "./helpers";

/** BotForge is provisioned per client — a stranger must not be able to hand themselves a
 * workspace. The old gate allowed every user their *first* org, so signing up on the public
 * form and accepting the "Create your organization" screen was a complete self-serve path.
 *
 * The server-side refusal is pinned by tests/test_org_creation_gate.py. What these cover is
 * the surface: nothing invites you to sign up, and a stray signup ends in a dead end rather
 * than a form that would 403.
 */

test("the login page doesn't advertise self-serve signup", async ({ page }) => {
  await page.goto("/login");

  await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();
  await expect(page.getByRole("link", { name: /create one/i })).toHaveCount(0);
  await expect(page.getByRole("link", { name: /sign up|create an account/i })).toHaveCount(0);
  await expect(page.getByText(/ask your botforge contact for an invitation/i)).toBeVisible();
});

test("a stray signup lands on the no-workspace dead end, not a create-org form", async ({
  page,
  context,
  request,
}) => {
  // Straight through the API: the point is the state a signed-up, org-less account lands in.
  const email = uniqueEmail("stray");
  const signup = await request.post(`${API}/v1/auth/signup`, {
    data: { email, password: "e2e-Password-123", full_name: "Stray Person" },
  });
  expect(signup.ok(), `signup failed: ${signup.status()}`).toBeTruthy();
  const auth = await signup.json();

  const host = new URL(WEB).hostname;
  await context.addCookies([
    { name: "bf_access", value: auth.access_token, domain: host, path: "/", sameSite: "Lax" },
    { name: "bf_refresh", value: auth.refresh_token, domain: host, path: "/", sameSite: "Lax" },
  ]);

  await page.goto("/dashboard");

  await expect(page.getByRole("heading", { name: /no workspace yet/i })).toBeVisible();
  // Their own address is named, so they know which one the invite has to go to.
  await expect(page.getByText(email)).toBeVisible();
  // The old form is gone — no way to self-provision from here.
  await expect(page.getByRole("button", { name: /create organization/i })).toHaveCount(0);
  await expect(page.getByLabel(/organization name/i)).toHaveCount(0);
});

test("an invited newcomer still gets in — the one legitimate route", async ({
  page,
  context,
  request,
}) => {
  // Staff-created host org. The E2E API runs with ALLOW_SELF_SERVE_ORGS so the suite can
  // bootstrap tenants; the production gate itself is covered by the backend suite.
  const ownerEmail = uniqueEmail("host");
  const owner = await request.post(`${API}/v1/auth/signup`, {
    data: { email: ownerEmail, password: "e2e-Password-123", full_name: "Host" },
  });
  const ownerAuth = await owner.json();
  const orgRes = await request.post(`${API}/v1/orgs`, {
    headers: { Authorization: `Bearer ${ownerAuth.access_token}` },
    data: { name: "Invite Host Workspace" },
  });
  expect(orgRes.ok(), `create org failed: ${orgRes.status()} ${await orgRes.text()}`).toBeTruthy();
  const org = await orgRes.json();

  const inviteeEmail = uniqueEmail("newcomer");
  const invite = await request.post(`${API}/v1/orgs/${org.id}/invitations`, {
    headers: { Authorization: `Bearer ${ownerAuth.access_token}`, "X-Org-Id": org.id },
    data: { email: inviteeEmail, role: "editor" },
  });
  expect(invite.ok(), `invite failed: ${invite.status()}`).toBeTruthy();
  const token = (await invite.json()).accept_token as string;
  expect(token, "dev API should expose accept_token").toBeTruthy();

  // Brand-new person, no account yet: signs up from the invite page itself.
  await page.goto(`/invitations/accept?token=${token}`);
  await page.getByLabel(/email/i).fill(inviteeEmail);
  await page.getByLabel(/password/i).fill("e2e-Password-123");
  await page.getByRole("button", { name: /create account & join/i }).click();

  await page.waitForURL("**/dashboard", { timeout: 20_000 });
  // They landed in the org, not on the dead end.
  await expect(page.getByRole("heading", { name: /no workspace yet/i })).toHaveCount(0);

  const cookies = await context.cookies();
  expect(cookies.find((c) => c.name === "bf_org")?.value).toBe(org.id);
});
