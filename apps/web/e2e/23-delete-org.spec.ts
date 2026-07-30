import { expect, test } from "@playwright/test";
import { API, auth, authenticateBrowser, createAccount } from "./helpers";

/** Deleting an organization from Settings → Organization.
 *
 * The risk here isn't the DELETE call, it's the state the app is left in: the org being
 * deleted is the active one, and its id lives in the `bf_org` cookie that every request
 * sends as `X-Org-Id`. If that isn't moved off, the session keeps pointing at a deleted org
 * and the *next* page is what breaks. So these assert the aftermath, not just the button.
 */

test("an owner deletes an org and the session moves to the one that's left", async ({
  page,
  context,
  request,
}) => {
  // The user owns the org they're about to delete, and belongs to a second one by invitation.
  // Not two self-created orgs: creating a second is staff-only (orgs.create_forbidden), and
  // being invited into several client workspaces is the realistic way an operator has more
  // than one anyway.
  const account = await createAccount(request, "Doomed Workspace");
  const host = await createAccount(request, "Keeper Workspace");

  const invite = await request.post(`${API}/v1/orgs/${host.orgId}/invitations`, {
    headers: { Authorization: `Bearer ${host.access}` },
    data: { email: account.email, role: "editor" },
  });
  expect(invite.ok(), `invite failed: ${invite.status()} ${await invite.text()}`).toBeTruthy();
  const token = (await invite.json()).accept_token as string;
  const accepted = await request.post(`${API}/v1/orgs/invitations/${token}/accept`, {
    headers: { Authorization: `Bearer ${account.access}` },
  });
  expect(accepted.ok(), `accept failed: ${accepted.status()}`).toBeTruthy();

  await authenticateBrowser(context, account); // bf_org = Doomed Workspace, which they own
  await page.goto("/settings/org");

  await expect(page.getByRole("heading", { name: "Danger zone" })).toBeVisible();
  await page.getByRole("button", { name: /delete organization/i }).click();

  const dialog = page.getByRole("dialog");
  const confirm = dialog.getByRole("button", { name: /delete organization/i });
  await expect(confirm).toBeDisabled();

  await dialog.getByLabel(/type doomed workspace to confirm/i).fill("Doomed Workspace");
  await expect(confirm).toBeEnabled();
  await confirm.click();

  await page.waitForURL("**/dashboard", { timeout: 15_000 });

  // The deleted org is gone from the server's list — the real check, not just the UI's word.
  const listed = await request.get(`${API}/v1/orgs`, { headers: auth(account) });
  const names = ((await listed.json()) as { name: string }[]).map((o) => o.name);
  expect(names).toContain("Keeper Workspace");
  expect(names).not.toContain("Doomed Workspace");

  // And the browser is no longer carrying the dead org id.
  const orgCookie = (await context.cookies()).find((c) => c.name === "bf_org");
  expect(orgCookie?.value).not.toBe(account.orgId);
});

test("a non-owner is never shown the danger zone", async ({ page, context, request }) => {
  const owner = await createAccount(request, "Owned Workspace");
  const member = await createAccount(request, "Member Own Workspace");

  // Invite the second user as an editor (the client role) and accept.
  const invite = await request.post(`${API}/v1/orgs/${owner.orgId}/invitations`, {
    headers: { Authorization: `Bearer ${owner.access}` },
    data: { email: member.email, role: "editor" },
  });
  expect(invite.ok(), `invite failed: ${invite.status()} ${await invite.text()}`).toBeTruthy();
  const token = (await invite.json()).accept_token as string;
  expect(token, "dev API should expose accept_token").toBeTruthy();

  const accepted = await request.post(`${API}/v1/orgs/invitations/${token}/accept`, {
    headers: { Authorization: `Bearer ${member.access}` },
  });
  expect(accepted.ok(), `accept failed: ${accepted.status()}`).toBeTruthy();

  await authenticateBrowser(context, { ...member, orgId: owner.orgId });
  await page.goto("/settings/org");

  // The page rendered, so the absence below is real rather than a blank screen.
  await expect(page.getByRole("heading", { name: "Organization profile" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Danger zone" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /delete organization/i })).toHaveCount(0);

  // The server refuses too — hiding a button is not access control.
  const forbidden = await request.delete(`${API}/v1/orgs/${owner.orgId}`, {
    headers: { Authorization: `Bearer ${member.access}`, "X-Org-Id": owner.orgId },
  });
  expect(forbidden.status()).toBe(403);
});
