import { expect, test } from "@playwright/test";
import { API, auth, authenticateBrowser, createAccount, type Account } from "./helpers";

/**
 * A knowledge base can be deleted from its own page.
 *
 * `DELETE /v1/knowledge/{id}` shipped in Phase 7 with nothing calling it, so a KB could be
 * created and never removed — only its documents could. Deleting one is quiet by design
 * (retrieval filters `deleted_at`), which is why the confirmation names the agents that would
 * be left answering without any context to ground them.
 */

let account: Account;

test.beforeAll(async ({ request }) => {
  account = await createAccount(request, "KB Delete Org");
});

test.beforeEach(async ({ context }) => {
  await authenticateBrowser(context, account);
});

async function createKb(request: import("@playwright/test").APIRequestContext, name: string) {
  const res = await request.post(`${API}/v1/knowledge`, { headers: auth(account), data: { name } });
  expect(res.status(), await res.text()).toBe(201);
  return (await res.json()).id as string;
}

test("an unused knowledge base is deleted and disappears from the list", async ({
  page,
  request,
}) => {
  const kbId = await createKb(request, "Disposable Docs");

  await page.goto(`/knowledge/${kbId}`);
  await page.getByRole("button", { name: "Delete knowledge base" }).click();
  await expect(page.getByText(/cannot be undone/i).first()).toBeVisible();
  await page.getByRole("button", { name: /OK, delete it/i }).click();

  await expect(page).toHaveURL(/\/knowledge$/);
  await expect(page.getByText("Disposable Docs")).toHaveCount(0);

  const listed = await (await request.get(`${API}/v1/knowledge`, { headers: auth(account) })).json();
  expect(listed.some((k: { id: string }) => k.id === kbId)).toBeFalsy();
});

test("the confirmation names a live agent that would lose its grounding", async ({
  page,
  request,
}) => {
  const kbId = await createKb(request, "Attached Docs");
  const agent = await (
    await request.post(`${API}/v1/agents`, { headers: auth(account), data: { name: "Grounded Bot" } })
  ).json();
  await request.patch(`${API}/v1/agents/${agent.id}/versions/1`, {
    headers: auth(account),
    data: { rag_config: { enabled: true, knowledge_base_ids: [kbId] } },
  });
  await request.post(`${API}/v1/agents/${agent.id}/versions/1/publish`, { headers: auth(account) });

  await page.goto(`/knowledge/${kbId}`);
  await page.getByRole("button", { name: "Delete knowledge base" }).click();

  await expect(page.getByText("Grounded Bot")).toBeVisible();
  await expect(page.getByText(/answers may be invented/i)).toBeVisible();

  // Backing out leaves everything alone — the warning has to be escapable.
  await page.getByRole("button", { name: "Cancel" }).click();
  const still = await (
    await request.get(`${API}/v1/knowledge/${kbId}`, { headers: auth(account) })
  ).json();
  expect(still.attached_agents).toHaveLength(1);
});
