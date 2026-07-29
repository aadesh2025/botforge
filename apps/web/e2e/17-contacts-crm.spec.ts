import { test, expect, type APIRequestContext } from "@playwright/test";
import { API, auth, authenticateBrowser, createAccount, type Account } from "./helpers";

/** Contacts appear as a side effect of people messaging an agent — there's no "create". */
async function seed(request: APIRequestContext, account: Account, people: [string, string][]) {
  const agent = await (
    await request.post(`${API}/v1/agents`, { headers: auth(account), data: { name: "CRM Bot" } })
  ).json();
  for (const [visitorId, name] of people) {
    const r = await request.post(`${API}/v1/public/agents/${agent.public_key}/chat`, {
      data: { message: "hello", stream: false, visitor: { id: visitorId, name } },
    });
    expect(r.status(), await r.text()).toBe(200);
  }
  return agent;
}

test("the contacts table lists, filters, and opens a detail panel", async ({ page, context, request }) => {
  const account = await createAccount(request, "CRM Org");
  await seed(request, account, [
    ["v-aadesh", "Aadesh Kumar"],
    ["v-rohak", "Rohak Arya"],
  ]);
  await authenticateBrowser(context, account);

  await page.goto("/contacts");
  await expect(page.getByRole("heading", { name: "Contacts" })).toBeVisible();

  const table = page.getByRole("table");
  await expect(table.getByRole("row", { name: /Aadesh Kumar/ })).toBeVisible();
  await expect(table.getByRole("row", { name: /Rohak Arya/ })).toBeVisible();

  // Search narrows the list server-side.
  await page.getByLabel("Search contacts").fill("aadesh");
  await expect(table.getByRole("row", { name: /Aadesh Kumar/ })).toBeVisible();
  await expect(table.getByRole("row", { name: /Rohak Arya/ })).toHaveCount(0);

  // Open the detail panel.
  await table.getByRole("row", { name: /Aadesh Kumar/ }).click();
  await expect(page.getByRole("heading", { name: "About" })).toBeVisible();

  // Lead stage persists and shows in the row.
  await page.getByLabel("Lead stage", { exact: true }).selectOption("qualified");
  await expect(table.getByRole("row", { name: /qualified/i })).toBeVisible();

  // A label round-trips as a chip.
  await page.getByLabel("New label").fill("vip");
  await page.getByRole("button", { name: "Add label" }).click();
  await expect(page.getByRole("button", { name: "Remove label vip" })).toBeVisible();

  // A note lands in the timeline.
  await page.getByLabel("New note").fill("Called — wants a quote on 200 units.");
  await page.getByRole("button", { name: "Add note" }).click();
  await expect(page.getByText("Called — wants a quote on 200 units.")).toBeVisible();

  // Filtering by the stage we just set keeps them, and excludes the other contact.
  await page.getByLabel("Search contacts").fill("");
  await page.getByLabel("Filter by lead stage").selectOption("qualified");
  await expect(table.getByRole("row", { name: /Aadesh Kumar/ })).toBeVisible();
  await expect(table.getByRole("row", { name: /Rohak Arya/ })).toHaveCount(0);
});

test("the inbox links a contact through to their CRM record", async ({ page, context, request }) => {
  const account = await createAccount(request, "CRM Link Org");
  const agent = await (
    await request.post(`${API}/v1/agents`, { headers: auth(account), data: { name: "Link Bot" } })
  ).json();
  await request.patch(`${API}/v1/agents/${agent.id}/versions/1`, {
    headers: auth(account),
    data: {
      fallback_message: "Connecting you to a teammate now.",
      features: { tools_enabled: false, memory_enabled: true, handoff_enabled: true },
    },
  });
  await request.post(`${API}/v1/public/agents/${agent.public_key}/chat`, {
    data: {
      message: "I want a human agent",
      stream: false,
      visitor: { id: "v-linked", name: "Linked Person" },
    },
  });

  await authenticateBrowser(context, account);
  await page.goto("/inbox");
  await page.getByRole("button", { name: /Linked Person/ }).first().click();

  await page.getByRole("link", { name: "Linked Person" }).click();
  await expect(page).toHaveURL(/\/contacts\//);
  // The panel opens straight onto that contact.
  await expect(page.getByRole("heading", { name: "About" })).toBeVisible();
  await expect(page.getByLabel("Lead stage", { exact: true })).toBeVisible();
});
