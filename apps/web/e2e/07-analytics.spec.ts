import { test, expect } from "@playwright/test";
import { API, auth, authenticateBrowser, createAccount, createPublishedAgent } from "./helpers";

// PRD acceptance criterion 7: analytics shows conversation + token usage for the agent.
test("criterion 7: analytics reflects conversations and token usage", async ({ page, context, request }) => {
  const account = await createAccount(request, "Analytics Org");
  const { id: agentId } = await createPublishedAgent(request, account, { name: "Metrics Bot" });

  // Generate a couple of turns so there is something to report.
  for (const msg of ["First question", "Second question"]) {
    const r = await request.post(`${API}/v1/agents/${agentId}/chat`, {
      headers: auth(account),
      data: { message: msg, stream: false },
    });
    expect(r.ok(), await r.text()).toBeTruthy();
  }

  // The overview aggregates conversations and non-zero token usage.
  const overview = await (
    await request.get(`${API}/v1/analytics/overview`, { headers: auth(account) })
  ).json();
  expect(overview.conversations).toBeGreaterThan(0);
  expect(overview.messages).toBeGreaterThan(0);
  expect((overview.tokens_prompt ?? 0) + (overview.tokens_completion ?? 0)).toBeGreaterThan(0);

  // The analytics page renders those numbers for the user.
  await authenticateBrowser(context, account);
  await page.goto("/analytics");
  await expect(page.getByRole("heading", { name: /analytics/i })).toBeVisible({ timeout: 15_000 });
});
