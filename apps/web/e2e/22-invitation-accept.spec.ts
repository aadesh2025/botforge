import { test, expect, type APIRequestContext } from "@playwright/test";
import { API, auth, authenticateBrowser, createAccount, uniqueEmail, type Account } from "./helpers";

// accept_invitation() was correct and complete server-side, but nothing in the web app ever
// called it — the email link had nowhere to land, so an invitation could never leave
// "pending" no matter what the recipient did. These cover the page that closes that gap.

/** Invite an email and return the raw token.
 *
 * The creation response already carries `accept_token` outside production, exactly so a
 * dev/CI flow can accept without a live inbox — no test-only endpoint needed.
 */
async function invite(
  request: APIRequestContext,
  owner: Account,
  email: string,
  role = "editor",
): Promise<string> {
  const res = await request.post(`${API}/v1/orgs/${owner.orgId}/invitations`, {
    headers: auth(owner),
    data: { email, role },
  });
  expect(res.status(), await res.text()).toBe(201);
  const body = await res.json();
  expect(body.accept_token, "dev/CI should expose the accept token").toBeTruthy();
  return body.accept_token as string;
}

/** Pending invitations only — the list filters out accepted ones, so absence proves
 *  `accepted_at` was set. */
async function pendingEmails(request: APIRequestContext, owner: Account): Promise<string[]> {
  const res = await request.get(`${API}/v1/orgs/${owner.orgId}/invitations`, {
    headers: auth(owner),
  });
  return (await res.json()).map((i: { email: string }) => i.email);
}

test("a brand-new user accepts an invitation and lands in the org", async ({ page, request }) => {
  const owner = await createAccount(request, "Invite Org");
  const inviteeEmail = uniqueEmail("invitee");
  const token = await invite(request, owner, inviteeEmail);

  expect(await pendingEmails(request, owner)).toContain(inviteeEmail);

  // The invitee has no account and no session — exactly the real case.
  await page.goto(`/invitations/accept?token=${token}`);
  await expect(page.getByRole("heading", { name: /You’ve been invited/ })).toBeVisible();

  await page.getByLabel("Your name").fill("New Teammate");
  await page.getByLabel("Email").fill(inviteeEmail);
  await page.getByLabel("Password").fill("invite-Password-123");
  await page.getByRole("button", { name: "Create account & join" }).click();

  // They land in the dashboard, with the org they joined active.
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 20_000 });
  await expect(page.getByText("Invite Org")).toBeVisible();

  // The invitation is accepted (gone from the pending list — that filter is on accepted_at)…
  await expect
    .poll(async () => await pendingEmails(request, owner))
    .not.toContain(inviteeEmail);

  // …and the membership is active with the invited role.
  const members = await (
    await request.get(`${API}/v1/orgs/${owner.orgId}/members`, { headers: auth(owner) })
  ).json();
  const member = members.find((m: { email: string }) => m.email === inviteeEmail);
  expect(member, "the invitee should now be a member").toBeTruthy();
  expect(member.status).toBe("active");
  expect(member.role).toBe("editor");
});

test("an existing user signs in from the invite page and joins", async ({ page, request }) => {
  const owner = await createAccount(request, "Invite Existing Org");
  // Someone who already has their own account and org.
  const existing = await createAccount(request, "Their Own Org");
  const token = await invite(request, owner, existing.email);

  await page.goto(`/invitations/accept?token=${token}`);
  await page.getByRole("button", { name: /I already have an account/ }).click();
  await page.getByLabel("Email").fill(existing.email);
  await page.getByLabel("Password").fill(existing.password);
  await page.getByRole("button", { name: "Sign in & join" }).click();

  await expect(page).toHaveURL(/\/dashboard/, { timeout: 20_000 });

  const members = await (
    await request.get(`${API}/v1/orgs/${owner.orgId}/members`, { headers: auth(owner) })
  ).json();
  expect(members.some((m: { email: string }) => m.email === existing.email)).toBeTruthy();
});

test("a signed-in user with the wrong email is told exactly that", async ({
  page,
  context,
  request,
}) => {
  const owner = await createAccount(request, "Invite Mismatch Org");
  const wrongPerson = await createAccount(request, "Somewhere Else");
  const token = await invite(request, owner, uniqueEmail("intended"));

  // Signed in as the wrong account.
  await authenticateBrowser(context, wrongPerson);
  await page.goto(`/invitations/accept?token=${token}`);

  await expect(page.getByRole("heading", { name: /different email/i })).toBeVisible();
  await expect(page.getByText(/Sign out and use the address/)).toBeVisible();
});

test("an invalid token says the invitation expired rather than failing vaguely", async ({
  page,
  context,
  request,
}) => {
  // Signed in, so the page actually attempts the accept and gets the server's verdict.
  const someone = await createAccount(request, "Bad Token Org");
  await authenticateBrowser(context, someone);

  await page.goto("/invitations/accept?token=not-a-real-token");
  await expect(page.getByRole("heading", { name: /expired/i })).toBeVisible();
  await expect(page.getByText(/valid for 7 days/)).toBeVisible();
});

test("no token at all is handled", async ({ page }) => {
  await page.goto("/invitations/accept");
  await expect(page.getByRole("heading", { name: /expired/i })).toBeVisible();
});
