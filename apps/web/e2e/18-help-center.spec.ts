import { test, expect } from "@playwright/test";
import { API, auth, authenticateBrowser, createAccount } from "./helpers";

// The Help Center is public-facing prose, separate from the AI's RAG store. Authoring is
// authenticated; reading is not — a visitor has no account.
test("an article is authored in the dashboard and served on the public page", async ({
  page,
  context,
  request,
}) => {
  const account = await createAccount(request, "Help Org");
  const agent = await (
    await request.post(`${API}/v1/agents`, { headers: auth(account), data: { name: "Help Bot" } })
  ).json();

  await authenticateBrowser(context, account);
  await page.goto("/knowledge/help-center");
  await expect(page.getByRole("heading", { name: "Help Center" })).toBeVisible();

  await page.getByLabel("Title").fill("How do refunds work?");
  await page.getByLabel("Category").fill("Billing");
  await page.getByLabel("Body (Markdown)").fill("## Refunds\n\nWe refund within **30 days**.");
  // Slug is derived from the title unless overridden.
  await expect(page.getByLabel("Slug")).toHaveAttribute("placeholder", "how-do-refunds-work");
  await page.getByLabel("Published").click();
  await page.getByRole("button", { name: "Create article" }).click();

  const articles = page.getByRole("list", { name: "Articles" });
  await expect(articles.getByText("/how-do-refunds-work")).toBeVisible();
  await expect(articles.getByText("Published")).toBeVisible();

  // ── The public page, with no session at all ──────────────────────────────────
  const anon = await page.context().browser()!.newContext();
  const anonPage = await anon.newPage();
  await anonPage.goto(`/help/${agent.public_key}`);
  await expect(anonPage.getByRole("heading", { name: "Help Center" })).toBeVisible();
  await expect(anonPage.getByText("Billing")).toBeVisible();

  await anonPage.getByRole("link", { name: "How do refunds work?" }).click();
  await expect(anonPage.getByRole("heading", { name: "How do refunds work?" })).toBeVisible();
  // The markdown is rendered, not shown raw.
  await expect(anonPage.getByRole("heading", { name: "Refunds", exact: true })).toBeVisible();
  await expect(anonPage.locator("strong", { hasText: "30 days" })).toBeVisible();
  await anon.close();
});

test("a draft is not visible publicly", async ({ page, context, request }) => {
  const account = await createAccount(request, "Help Draft Org");
  const agent = await (
    await request.post(`${API}/v1/agents`, { headers: auth(account), data: { name: "Draft Bot" } })
  ).json();
  await request.post(`${API}/v1/help-articles`, {
    headers: auth(account),
    data: { agent_id: agent.id, title: "Internal only", body_markdown: "secret", published: false },
  });

  await authenticateBrowser(context, account);
  await page.goto(`/help/${agent.public_key}`);
  await expect(page.getByText("No articles have been published yet.")).toBeVisible();
  await expect(page.getByText("Internal only")).toHaveCount(0);

  // Guessing the slug doesn't reveal it either.
  const direct = await request.get(`${API}/v1/public/agents/${agent.public_key}/help/internal-only`);
  expect(direct.status()).toBe(404);
});

test("syncing to the AI is refused when the agent has no knowledge base", async ({
  page,
  context,
  request,
}) => {
  const account = await createAccount(request, "Help Sync Org");
  await request.post(`${API}/v1/agents`, { headers: auth(account), data: { name: "No KB Bot" } });

  await authenticateBrowser(context, account);
  await page.goto("/knowledge/help-center");

  await page.getByLabel("Title").fill("Orphan article");
  await page.getByLabel("Body (Markdown)").fill("body");
  await page.getByLabel("Published").click();
  await page.getByLabel("Also teach the AI").click();
  await page.getByRole("button", { name: "Create article" }).click();

  // Told why, rather than silently writing into a store the agent never reads.
  await expect(page.getByText(/no knowledge base to sync into/i)).toBeVisible();
});
