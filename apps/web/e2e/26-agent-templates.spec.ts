import { expect, test } from "@playwright/test";
import { API, auth, authenticateBrowser, createAccount, type Account } from "./helpers";

/**
 * Creating an agent starts from a role template.
 *
 * The "New agent" dialog used to be a single name field producing a generic blank draft.
 * It now offers four prebuilt roles — each seeding the first draft's system prompt, welcome
 * message, suggested prompts, tone and model settings — plus a "Start from scratch" option
 * that must keep behaving exactly as it always did.
 *
 * One account for the whole file: the suite already brushes up against `AUTH_RATE_LIMIT` on
 * a full back-to-back run (see the roadmap note in docs/PROGRESS.md).
 */

let account: Account;

test.beforeAll(async ({ request }) => {
  account = await createAccount(request, "Templates Org");
});

test.beforeEach(async ({ context }) => {
  await authenticateBrowser(context, account);
});

/** The page has two entry points ("New agent" in the header, "Create a new agent" card), and
 *  the card's name contains the header's — so the header button needs an exact match. */
const openDialog = (page: import("@playwright/test").Page) =>
  page.getByRole("button", { name: "New agent", exact: true }).click();

const templateCard = (page: import("@playwright/test").Page, label: string) =>
  page.getByRole("button", { name: new RegExp(`^${label}`) });

test("the picker offers every role plus a start-from-scratch option", async ({ page }) => {
  await page.goto("/agents");
  await openDialog(page);

  await expect(page.getByText("What should this agent do?")).toBeVisible();
  for (const label of [
    "Customer Support",
    "Lead Qualification",
    "Appointment Scheduler",
    "Info Collector",
  ]) {
    await expect(templateCard(page, label)).toBeVisible();
  }
  await expect(page.getByText("Start from scratch")).toBeVisible();
});

test("the dialog stays inside the viewport and is reachable end to end", async ({ page }) => {
  // Regression: `animate-fade-up` ends on `transform: translateY(0)` with fill-mode `both`,
  // which overrode DialogContent's `-translate-x-1/2 -translate-y-1/2` centering. Every
  // dialog was anchored at the viewport centre instead of centred on it; small ones still
  // fit, but this taller picker was clipped and "Start from scratch" could not be clicked.
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto("/agents");
  await openDialog(page);

  const dialog = page.getByRole("dialog");
  const box = await dialog.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.y).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(1280);
  expect(box!.y + box!.height).toBeLessThanOrEqual(720);
  // Roughly horizontally centred, rather than starting at the midpoint.
  expect(Math.abs(box!.x + box!.width / 2 - 640)).toBeLessThan(20);

  await expect(page.getByText("Start from scratch")).toBeVisible();
});

test("creating from a template lands in the Persona tab with its prompt filled in", async ({
  page,
}) => {
  await page.goto("/agents");
  await openDialog(page);
  await templateCard(page, "Customer Support").click();

  // The name is pre-filled with the role, and stays editable.
  const name = page.getByLabel("Agent name");
  await expect(name).toHaveValue("Customer Support");
  await name.fill("Front Desk");
  await page.getByRole("button", { name: /Create & configure/ }).click();

  await page.waitForURL(/\/agents\/[0-9a-f-]+\?tab=persona/);

  // The template's persona is present and editable — a starting point, not a locked preset.
  const prompt = page.locator("textarea").first();
  await expect(prompt).toHaveValue(/customer-support agent/);
  await expect(prompt).toBeEditable();
  await expect(page.locator("textarea").nth(1)).toHaveValue("Hi! What can I help you with today?");

  // Its suggested prompts came across as chips.
  await expect(page.getByText("What's your refund policy?")).toBeVisible();

  // And the role's next step is surfaced as a hint, not silently configured.
  await expect(page.getByText(/Suggested next step/)).toBeVisible();
  await expect(page.getByText(/Attach a knowledge base/)).toBeVisible();
});

test("start from scratch still creates a plain agent with no template hint", async ({ page }) => {
  await page.goto("/agents");
  await openDialog(page);
  await page.getByText("Start from scratch").click();

  const name = page.getByLabel("Agent name");
  await expect(name).toHaveValue(""); // no role, so no suggested name
  await name.fill("Blank Bot");
  await page.getByRole("button", { name: /Create & configure/ }).click();

  await page.waitForURL(/\/agents\/[0-9a-f-]+\?tab=persona/);

  // The stock default prompt, and none of the template scaffolding.
  await expect(page.locator("textarea").first()).toHaveValue(/customer-support assistant/);
  await expect(page.getByText(/Suggested next step/)).toHaveCount(0);
});

test("each template seeds a distinct draft through the API", async ({ request }) => {
  const templatesRes = await request.get(`${API}/v1/agent-templates`, { headers: auth(account) });
  expect(templatesRes.ok(), `templates failed: ${await templatesRes.text()}`).toBeTruthy();
  const templates = await templatesRes.json();
  expect(templates).toHaveLength(4);

  for (const template of templates) {
    const created = await request.post(`${API}/v1/agents`, {
      headers: auth(account),
      data: { name: `Seeded ${template.id}`, template_id: template.id },
    });
    expect(created.ok(), `create failed: ${await created.text()}`).toBeTruthy();
    const agent = await created.json();

    const versions = await request.get(`${API}/v1/agents/${agent.id}/versions`, {
      headers: auth(account),
    });
    const draft = (await versions.json())[0];

    expect(draft.system_prompt).toBe(template.system_prompt);
    expect(draft.welcome_message).toBe(template.welcome_message);
    expect(draft.suggested_prompts).toEqual(template.suggested_prompts);
    expect(draft.persona).toEqual({ tone: template.tone, template_id: template.id });
    // No template may reintroduce the citation-list voice Part 1 removed.
    expect(template.system_prompt.toLowerCase()).not.toContain("cite sources");
  }
});
