import { test, expect } from "@playwright/test";
import { API, auth, authenticateBrowser, createAccount } from "./helpers";

// The CRM lists *people*. A person appears once we can identify them — they shared an email
// or phone, or an operator added them by hand.

test("a contact can be added by hand from the CRM", async ({ page, context, request }) => {
  const account = await createAccount(request, "CRM Manual Org");
  await authenticateBrowser(context, account);

  await page.goto("/contacts");
  await expect(page.getByRole("heading", { name: "CRM" })).toBeVisible();
  await expect(page.getByText(/No contacts yet/)).toBeVisible();

  await page.getByRole("button", { name: "New contact" }).click();
  await page.getByLabel("Name").fill("Walk-in Customer");
  await page.getByLabel("Email").fill("Walkin@Example.com");
  await page.getByLabel("Phone").fill("+91 98765 43210");
  await page.getByLabel("Lead stage", { exact: true }).selectOption("contacted");
  await page.getByRole("button", { name: "Add contact" }).click();

  const table = page.getByRole("table");
  await expect(table.getByRole("row", { name: /Walk-in Customer/ })).toBeVisible();
  // Origin is visible in the channels column. (Also in the avatar's screen-reader text,
  // hence first().)
  await expect(table.getByText("Added manually").first()).toBeVisible();

  // The detail panel opens on the new contact, with the details normalised.
  // Scoped to the panel: the email also appears in the table row behind it.
  const panel = page.getByRole("complementary", { name: "Contact details" });
  await expect(panel.getByRole("heading", { name: "About" })).toBeVisible();
  await expect(panel).toContainText("walkin@example.com");
  await expect(panel).toContainText("+919876543210");

  // …and the sidebar item is renamed too.
  await expect(page.getByRole("link", { name: "CRM" })).toBeVisible();
});

test("the auto-capture toggle is on by default and can be switched off", async ({
  page,
  context,
  request,
}) => {
  const account = await createAccount(request, "CRM Toggle Org");
  await authenticateBrowser(context, account);

  await page.goto("/settings/org");
  await expect(page.getByRole("heading", { name: "Automatic CRM capture" })).toBeVisible();
  await expect(
    page.getByText(/Automatically detect names, emails, and phone numbers/),
  ).toBeVisible();

  const toggle = page.getByLabel("Automatic CRM capture");
  await expect(toggle).toBeChecked();

  await toggle.click();
  await expect(toggle).not.toBeChecked();

  // Persisted, not just local state.
  await expect
    .poll(async () => {
      const orgs = await (await request.get(`${API}/v1/orgs`, { headers: auth(account) })).json();
      return orgs[0].auto_crm_capture_enabled;
    })
    .toBe(false);

  await page.reload();
  await expect(page.getByLabel("Automatic CRM capture")).not.toBeChecked();
});

test("a customer who shares an email is recognised on a second channel", async ({
  page,
  context,
  request,
}) => {
  const account = await createAccount(request, "CRM Capture Org");
  const agent = await (
    await request.post(`${API}/v1/agents`, { headers: auth(account), data: { name: "Capture Bot" } })
  ).json();

  // Two separate visitor identities — two `Contact` rows — sharing one email.
  for (const visitorId of ["v-first", "v-second"]) {
    const r = await request.post(`${API}/v1/public/agents/${agent.public_key}/chat`, {
      data: {
        message: "I'm Meera, you can reach me at meera@example.com",
        stream: false,
        visitor: { id: visitorId },
      },
    });
    expect(r.status(), await r.text()).toBe(200);
  }

  await authenticateBrowser(context, account);
  await page.goto("/contacts");

  // One person, not two.
  const rows = page.getByRole("table").getByRole("row");
  await expect(rows).toHaveCount(2); // header + one person
  await page.getByRole("table").getByRole("row", { name: /meera@example.com|Meera/ }).click();

  const panel = page.getByRole("complementary", { name: "Contact details" });
  await expect(panel.getByRole("heading", { name: "About" })).toBeVisible();
  await expect(panel).toContainText("meera@example.com");
  // Both handles hang off the one person.
  await expect(panel).toContainText("v-first");
  await expect(panel).toContainText("v-second");
});
