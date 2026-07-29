import { test, expect, type APIRequestContext } from "@playwright/test";
import { API, auth, authenticateBrowser, createAccount, type Account } from "./helpers";

// The CRM lists *people*. Someone appears once we can identify them — they shared an email
// or phone, or an operator added them by hand. A visitor who only says "hi" stays in the
// Inbox as a per-channel handle.

/** Seed people by having visitors share an email, which is what creates a CRM record. */
async function seed(request: APIRequestContext, account: Account, people: [string, string, string][]) {
  const agent = await (
    await request.post(`${API}/v1/agents`, { headers: auth(account), data: { name: "CRM Bot" } })
  ).json();
  for (const [visitorId, name, email] of people) {
    const r = await request.post(`${API}/v1/public/agents/${agent.public_key}/chat`, {
      data: { message: `hello, ${email}`, stream: false, visitor: { id: visitorId, name } },
    });
    expect(r.status(), await r.text()).toBe(200);
  }
  return agent;
}

test("the CRM table lists, filters, and opens a detail panel", async ({ page, context, request }) => {
  const account = await createAccount(request, "CRM Org");
  await seed(request, account, [
    ["v-aadesh", "Aadesh Kumar", "aadesh@example.com"],
    ["v-rohak", "Rohak Arya", "rohak@example.com"],
  ]);
  await authenticateBrowser(context, account);

  await page.goto("/contacts");
  await expect(page.getByRole("heading", { name: "CRM" })).toBeVisible();

  const table = page.getByRole("table");
  await expect(table.getByRole("row", { name: /Aadesh Kumar/ })).toBeVisible();
  await expect(table.getByRole("row", { name: /Rohak Arya/ })).toBeVisible();

  // Search narrows the list server-side.
  await page.getByLabel("Search contacts").fill("aadesh");
  await expect(table.getByRole("row", { name: /Aadesh Kumar/ })).toBeVisible();
  await expect(table.getByRole("row", { name: /Rohak Arya/ })).toHaveCount(0);

  await table.getByRole("row", { name: /Aadesh Kumar/ }).click();
  const panel = page.getByRole("complementary", { name: "Contact details" });
  await expect(panel.getByRole("heading", { name: "About" })).toBeVisible();
  await expect(panel).toContainText("aadesh@example.com");

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

  // Filtering by the stage we just set keeps them, and excludes the other person.
  await page.getByLabel("Search contacts").fill("");
  await page.getByLabel("Filter by lead stage").selectOption("qualified");
  await expect(table.getByRole("row", { name: /Aadesh Kumar/ })).toBeVisible();
  await expect(table.getByRole("row", { name: /Rohak Arya/ })).toHaveCount(0);
});

test("the inbox links a recognised contact through to their CRM record", async ({
  page,
  context,
  request,
}) => {
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
  // Shares an email *and* escalates, so there's both a CRM person and an inbox item.
  await request.post(`${API}/v1/public/agents/${agent.public_key}/chat`, {
    data: {
      message: "linked@example.com — I want a human agent",
      stream: false,
      visitor: { id: "v-linked", name: "Linked Person" },
    },
  });

  await authenticateBrowser(context, account);
  await page.goto("/inbox");
  await page.getByRole("button", { name: /Linked Person/ }).first().click();

  // The name links through to the *person*, not the per-channel handle.
  await page.getByRole("link", { name: "Linked Person" }).click();
  await expect(page).toHaveURL(/\/contacts\//);
  const panel = page.getByRole("complementary", { name: "Contact details" });
  await expect(panel.getByRole("heading", { name: "About" })).toBeVisible();
  await expect(panel).toContainText("linked@example.com");
});
