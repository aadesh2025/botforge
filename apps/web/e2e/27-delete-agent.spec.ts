import { expect, test } from "@playwright/test";
import { API, auth, authenticateBrowser, createAccount, createPublishedAgent } from "./helpers";

/** Deleting an agent from the builder's Settings tab.
 *
 * The button existed as markup from Phase 4 with no `onClick` at all, so it was inert —
 * `deleteAgent()` was in the API client and nothing called it. These assert the two halves
 * that were missing: the confirmation step actually gates the call, and the agent is gone
 * from the *server's* list afterwards rather than just from the screen.
 */

test("an owner deletes an agent after confirming, and it leaves the list", async ({
  page,
  context,
  request,
}) => {
  // Org name deliberately shares no words with the button: the org switcher is a button too,
  // and "Delete Agent Org" made `/delete agent/i` ambiguous.
  const account = await createAccount(request, "Agent Removal Workspace");
  const doomed = await createPublishedAgent(request, account, { name: "Doomed Agent" });
  const keeper = await createPublishedAgent(request, account, { name: "Keeper Agent" });

  await authenticateBrowser(context, account);
  await page.goto(`/agents/${doomed.id}?tab=settings`);

  await expect(page.getByRole("heading", { name: "Danger zone" })).toBeVisible();

  // Nothing is deleted by opening the dialog — the first click only asks.
  await page.getByRole("button", { name: "Delete agent", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText(/press ok to delete this agent/i)).toBeVisible();

  // Cancelling leaves the agent alone: the point of a confirmation.
  await dialog.getByRole("button", { name: /cancel/i }).click();
  const stillThere = await request.get(`${API}/v1/agents/${doomed.id}`, { headers: auth(account) });
  expect(stillThere.status()).toBe(200);

  await page.getByRole("button", { name: "Delete agent", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: /ok, delete agent/i }).click();

  await page.waitForURL("**/agents", { timeout: 15_000 });

  // The server is the real check, not the redirect.
  const gone = await request.get(`${API}/v1/agents/${doomed.id}`, { headers: auth(account) });
  expect(gone.status()).toBe(404);

  const listed = await request.get(`${API}/v1/agents`, { headers: auth(account) });
  const names = ((await listed.json()) as { name: string }[]).map((a) => a.name);
  expect(names).toContain("Keeper Agent");
  expect(names).not.toContain("Doomed Agent");

  // And the deleted card is not left behind in the rendered list.
  await expect(page.getByRole("heading", { name: "Keeper Agent" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Doomed Agent" })).toHaveCount(0);
  expect(keeper.id).toBeTruthy();
});

test("a viewer is never shown the danger zone", async ({ page, context, request }) => {
  const owner = await createAccount(request, "Agent Owner Org");
  const viewer = await createAccount(request, "Viewer Own Org");
  const agent = await createPublishedAgent(request, owner, { name: "Read Only Agent" });

  const invite = await request.post(`${API}/v1/orgs/${owner.orgId}/invitations`, {
    headers: { Authorization: `Bearer ${owner.access}` },
    data: { email: viewer.email, role: "viewer" },
  });
  expect(invite.ok(), `invite failed: ${invite.status()} ${await invite.text()}`).toBeTruthy();
  const token = (await invite.json()).accept_token as string;
  const accepted = await request.post(`${API}/v1/orgs/invitations/${token}/accept`, {
    headers: { Authorization: `Bearer ${viewer.access}` },
  });
  expect(accepted.ok(), `accept failed: ${accepted.status()}`).toBeTruthy();

  await authenticateBrowser(context, { ...viewer, orgId: owner.orgId });
  await page.goto(`/agents/${agent.id}?tab=settings`);

  // The tab rendered, so the absence below is real rather than a blank screen.
  await expect(page.getByText("Basic details for this agent.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Danger zone" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Delete agent", exact: true })).toHaveCount(0);

  // The server refuses too — hiding a button is not access control.
  const forbidden = await request.delete(`${API}/v1/agents/${agent.id}`, {
    headers: { Authorization: `Bearer ${viewer.access}`, "X-Org-Id": owner.orgId },
  });
  expect(forbidden.status()).toBe(403);
});
