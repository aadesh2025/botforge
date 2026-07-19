import { test, expect } from "@playwright/test";
import { API, auth, authenticateBrowser, createAccount, createPublishedAgent } from "./helpers";

// PRD acceptance criterion 4: connect Telegram and chat with the same agent there.
// The signed inbound webhook is verified (secret-token), routed to the agent, and the reply
// is persisted. Real Telegram delivery is unreachable from CI and is non-fatal by design.
test("criterion 4: signed Telegram inbound produces an agent reply", async ({ page, context, request }) => {
  const account = await createAccount(request, "Telegram Org");
  const { id: agentId } = await createPublishedAgent(request, account, { name: "TG Bot" });

  // Connect a Telegram channel.
  const chRes = await request.post(`${API}/v1/channels`, {
    headers: auth(account),
    data: { agent_id: agentId, type: "telegram", config: { bot_token: "123456:E2E-TEST-TOKEN" } },
  });
  expect(chRes.ok(), await chRes.text()).toBeTruthy();
  const channel = await chRes.json();
  expect(channel.webhook_secret, "owner should see the webhook secret").toBeTruthy();

  // Channels start disabled; enable it so inbound updates are processed.
  const en = await request.post(`${API}/v1/channels/${channel.id}/enable`, { headers: auth(account) });
  expect(en.ok(), await en.text()).toBeTruthy();

  // Deliver a signed inbound update, exactly as Telegram would.
  const inbound = await request.post(`${API}/v1/channels/telegram/${channel.id}/webhook`, {
    headers: { "x-telegram-bot-api-secret-token": channel.webhook_secret },
    data: { message: { chat: { id: 4242 }, text: "hello telegram" } },
  });
  expect(inbound.status(), await inbound.text()).toBe(200);

  // A bad secret must be rejected.
  const bad = await request.post(`${API}/v1/channels/telegram/${channel.id}/webhook`, {
    headers: { "x-telegram-bot-api-secret-token": "wrong-secret" },
    data: { message: { chat: { id: 1 }, text: "spoof" } },
  });
  expect(bad.status()).toBe(401);

  // The turn was persisted on a telegram conversation with the agent's echo reply.
  const convs = await (await request.get(`${API}/v1/conversations`, { headers: auth(account) })).json();
  const tg = convs.find((c: { channel?: string }) => c.channel === "telegram") ?? convs[0];
  expect(tg, "a conversation should exist").toBeTruthy();
  const detail = await (
    await request.get(`${API}/v1/conversations/${tg.id}`, { headers: auth(account) })
  ).json();
  const texts = (detail.messages ?? []).map((m: { content: string }) => m.content).join(" ");
  expect(texts).toContain("echo: hello telegram");

  // The operator inbox renders (realtime hub-backed UI smoke).
  await authenticateBrowser(context, account);
  await page.goto("/inbox");
  await expect(page.getByRole("heading", { name: /inbox/i })).toBeVisible();
});
