import { test, expect } from "@playwright/test";
import { API, auth, authenticateBrowser, createAccount } from "./helpers";

// A channel breakdown is only useful if it tells the truth about a channel nobody has
// messaged yet — the near-term reality is WhatsApp/Instagram going live with real Meta
// credentials days before the first real conversation. So: one populated channel, one
// connected-but-empty channel, and both must read correctly everywhere.
test("channel breakdown reports a populated channel and a connected-but-empty one", async ({
  page,
  context,
  request,
}) => {
  const account = await createAccount(request, "Channel Analytics Org");

  const create = await request.post(`${API}/v1/agents`, {
    headers: auth(account),
    data: { name: "Metrics Bot" },
  });
  expect(create.ok(), await create.text()).toBeTruthy();
  const agent = await create.json();

  // Connect Instagram and enable it, but never deliver a message through it.
  const ch = await request.post(`${API}/v1/channels`, {
    headers: auth(account),
    data: { agent_id: agent.id, type: "instagram", config: {} },
  });
  expect(ch.ok(), await ch.text()).toBeTruthy();
  const enabled = await request.post(`${API}/v1/channels/${(await ch.json()).id}/enable`, {
    headers: auth(account),
  });
  expect(enabled.ok(), await enabled.text()).toBeTruthy();

  // Real traffic on the dashboard channel.
  const chat = await request.post(`${API}/v1/agents/${agent.id}/chat`, {
    headers: auth(account),
    data: { message: "how much does it cost?", stream: false },
  });
  expect(chat.ok(), await chat.text()).toBeTruthy();

  // The API reports both, with no divide-by-zero on the silent one.
  const overview = await (
    await request.get(`${API}/v1/analytics/overview`, { headers: auth(account) })
  ).json();
  const byChannel: Record<string, { conversations: number; resolution_rate: number }> =
    Object.fromEntries(overview.by_channel.map((b: { channel: string }) => [b.channel, b]));
  expect(byChannel.instagram, "an enabled channel reports even with no traffic").toBeTruthy();
  expect(byChannel.instagram.conversations).toBe(0);
  expect(byChannel.instagram.resolution_rate).toBe(0);
  expect(byChannel.dashboard.conversations).toBe(1);

  // The CSV export carries the same zero row.
  const csv = await request.get(`${API}/v1/analytics/export?type=channels`, { headers: auth(account) });
  expect(csv.status()).toBe(200);
  const csvText = await csv.text();
  expect(csvText.split("\n")[0]).toContain("channel,conversations,messages");
  expect(csvText).toContain("instagram,0,0,0,0,0,0.0,0.0");

  // ── Dashboard ────────────────────────────────────────────────────────────────
  await authenticateBrowser(context, account);
  await page.goto("/dashboard");

  const dashSection = page.getByRole("region", { name: "By channel" });
  await expect(dashSection).toBeVisible();

  // The populated channel shows its real count…
  const dashDashboardRow = dashSection.getByRole("row", { name: /Dashboard/ });
  await expect(dashDashboardRow).toBeVisible();
  await expect(dashDashboardRow.getByText("1", { exact: true })).toBeVisible();
  await expect(dashDashboardRow.getByText("100%")).toBeVisible();

  // …and the silent one is present, flagged, and shows a dash rather than "0%".
  const dashInstagramRow = dashSection.getByRole("row", { name: /Instagram/ });
  await expect(dashInstagramRow).toBeVisible();
  await expect(dashInstagramRow.getByText("no traffic")).toBeVisible();
  await expect(dashInstagramRow.getByText("—")).toBeVisible();

  // Nothing rendered as NaN/undefined anywhere in the section.
  const dashText = (await dashSection.textContent()) ?? "";
  expect(dashText).not.toContain("NaN");
  expect(dashText).not.toContain("undefined");

  // ── Analytics page ───────────────────────────────────────────────────────────
  await page.goto("/analytics");
  const anSection = page.getByRole("region", { name: "By channel" });
  await expect(anSection).toBeVisible();
  await expect(anSection.getByRole("row", { name: /Instagram/ })).toBeVisible();
  await expect(anSection.getByRole("row", { name: /Dashboard/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Export channels/ })).toBeVisible();

  const anText = (await anSection.textContent()) ?? "";
  expect(anText).not.toContain("NaN");
  expect(anText).not.toContain("undefined");
});
