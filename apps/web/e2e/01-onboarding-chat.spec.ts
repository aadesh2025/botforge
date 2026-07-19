import { test, expect } from "@playwright/test";
import { uniqueEmail } from "./helpers";

// PRD acceptance criterion 1: a new user can sign up, create an org, create an agent,
// pick Groq, and chat with it — driven entirely through the browser UI.
test("criterion 1: signup → create org → create agent → chat", async ({ page }) => {
  const email = uniqueEmail("onboard");

  // Sign up.
  await page.goto("/signup");
  await page.getByLabel("Full name").fill("E2E Onboarder");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("e2e-Password-123");
  await page.getByRole("button", { name: /create account/i }).click();

  // First-run: create the organization.
  await expect(page.getByRole("heading", { name: /create your organization/i })).toBeVisible();
  await page.getByLabel(/organization name/i).fill("E2E Workspace");
  await page.getByRole("button", { name: /create organization/i }).click();

  // Land on the dashboard.
  await expect(page).toHaveURL(/\/dashboard/);

  // Create an agent.
  await page.goto("/agents");
  await page.getByRole("button", { name: /new agent/i }).first().click();
  await page.getByPlaceholder(/agent name/i).fill("Support Bot");
  await page.getByRole("button", { name: /create & configure/i }).click();

  // Builder loads for the new agent.
  await expect(page).toHaveURL(/\/agents\/[0-9a-f-]+/);

  // The default provider is Groq — the playground footer shows the model label.
  await expect(page.getByText(/Groq/i).first()).toBeVisible();

  // Chat in the playground (deterministic Fake provider echoes the message in CI).
  const composer = page.getByPlaceholder(/message the draft agent/i);
  await composer.fill("Ping E2E");
  await composer.press("Enter");

  await expect(page.getByText(/echo:\s*Ping E2E/i)).toBeVisible({ timeout: 20_000 });
});
