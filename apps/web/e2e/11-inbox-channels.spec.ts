import { createHmac } from "node:crypto";
import { test, expect, type APIRequestContext } from "@playwright/test";
import { API, auth, authenticateBrowser, createAccount, type Account } from "./helpers";

const APP_SECRET = "e2e-meta-app-secret";
const IGSID = "17841400000000042";
const TG_CHAT = "778899";

/** Sign a webhook body exactly as Meta does, so the adapter's HMAC check passes. */
function metaHeaders(body: string): Record<string, string> {
  const sig = createHmac("sha256", APP_SECRET).update(body).digest("hex");
  return { "x-hub-signature-256": `sha256=${sig}`, "content-type": "application/json" };
}

/** An agent that escalates on a handoff keyword — that's what fills the operator queue. */
async function createHandoffAgent(request: APIRequestContext, account: Account): Promise<string> {
  const create = await request.post(`${API}/v1/agents`, {
    headers: auth(account),
    data: { name: "Inbox Bot" },
  });
  expect(create.ok(), await create.text()).toBeTruthy();
  const agent = await create.json();
  const patch = await request.patch(`${API}/v1/agents/${agent.id}/versions/1`, {
    headers: auth(account),
    data: {
      fallback_message: "Connecting you to a teammate now.",
      features: { tools_enabled: false, memory_enabled: true, handoff_enabled: true },
    },
  });
  expect(patch.ok(), await patch.text()).toBeTruthy();
  return agent.id;
}

async function connect(
  request: APIRequestContext,
  account: Account,
  agentId: string,
  type: string,
  config: Record<string, string>,
): Promise<{ id: string; webhook_secret: string }> {
  const res = await request.post(`${API}/v1/channels`, {
    headers: auth(account),
    data: { agent_id: agentId, type, config },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
  const channel = await res.json();
  const en = await request.post(`${API}/v1/channels/${channel.id}/enable`, { headers: auth(account) });
  expect(en.ok(), await en.text()).toBeTruthy();
  return channel;
}

// The unified inbox: conversations from two different platforms land in one queue, each
// resolved to a Contact, behind per-channel tabs that exist only for connected channels.
test("unified inbox: per-channel tabs and contact identity", async ({ page, context, request }) => {
  const account = await createAccount(request, "Unified Inbox Org");
  const agentId = await createHandoffAgent(request, account);

  // No real Meta credentials in CI: with the page token absent the Graph profile lookup
  // and the outbound send are skipped with a warning (CLAUDE.md §7) while the inbound
  // path under test runs for real. Telegram carries the sender's name in the update
  // itself, so that's where the rendered-name assertions live.
  const ig = await connect(request, account, agentId, "instagram", {
    app_secret: APP_SECRET,
    verify_token: "e2e-verify",
  });
  const tg = await connect(request, account, agentId, "telegram", { bot_token: "123456:E2E" });

  // Meta's GET subscription handshake.
  const challenge = await request.get(
    `${API}/v1/channels/instagram/${ig.id}/webhook` +
      `?hub.mode=subscribe&hub.verify_token=e2e-verify&hub.challenge=E2ECHAL`,
  );
  expect(challenge.status()).toBe(200);
  expect(await challenge.text()).toBe("E2ECHAL");

  // Signed Instagram DM.
  const body = JSON.stringify({
    object: "instagram",
    entry: [
      { id: "PAGE1", messaging: [{ sender: { id: IGSID }, message: { text: "I need a human agent" } }] },
    ],
  });
  const inbound = await request.post(`${API}/v1/channels/instagram/${ig.id}/webhook`, {
    headers: metaHeaders(body),
    data: body,
  });
  expect(inbound.status(), await inbound.text()).toBe(200);

  // A forged signature is rejected.
  const spoof = await request.post(`${API}/v1/channels/instagram/${ig.id}/webhook`, {
    headers: { "x-hub-signature-256": "sha256=deadbeef", "content-type": "application/json" },
    data: body,
  });
  expect(spoof.status()).toBe(401);

  // Telegram message from a named sender.
  const tgInbound = await request.post(`${API}/v1/channels/telegram/${tg.id}/webhook`, {
    headers: { "x-telegram-bot-api-secret-token": tg.webhook_secret },
    data: {
      message: {
        chat: { id: Number(TG_CHAT) },
        from: { id: Number(TG_CHAT), first_name: "Aadesh", last_name: "S", username: "aadeshx" },
        text: "can I talk to a human please?",
      },
    },
  });
  expect(tgInbound.status(), await tgInbound.text()).toBe(200);

  // The API scopes the queue per channel and attaches the resolved contact.
  const igItems = await (
    await request.get(`${API}/v1/inbox/conversations?channel=instagram`, { headers: auth(account) })
  ).json();
  expect(igItems).toHaveLength(1);
  expect(igItems[0].channel).toBe("instagram");
  expect(igItems[0].contact, "every inbound resolves to a contact").toBeTruthy();

  const tgItems = await (
    await request.get(`${API}/v1/inbox/conversations?channel=telegram`, { headers: auth(account) })
  ).json();
  expect(tgItems).toHaveLength(1);
  expect(tgItems[0].contact.display_name).toBe("Aadesh S");

  // ── The operator's view ──────────────────────────────────────────────────────
  await authenticateBrowser(context, account);
  await page.goto("/inbox");
  await expect(page.getByRole("heading", { name: /inbox/i })).toBeVisible();

  // A tab per connected+enabled channel; Web Chat always; WhatsApp (unconnected) never.
  const tabs = page.getByRole("tablist", { name: "Channels" });
  await expect(tabs.getByRole("tab", { name: "Web Chat" })).toBeVisible();
  await expect(tabs.getByRole("tab", { name: /Instagram/ })).toBeVisible();
  await expect(tabs.getByRole("tab", { name: /Telegram/ })).toBeVisible();
  await expect(tabs.getByRole("tab", { name: /WhatsApp/ })).toHaveCount(0);

  // Telegram: the list row shows the contact's real name badged with the platform…
  await tabs.getByRole("tab", { name: /Telegram/ }).click();
  const tgRow = page.getByRole("button", { name: /Aadesh S on Telegram/ });
  await expect(tgRow).toBeVisible();
  // …and opening it carries the same identity into the thread header.
  await tgRow.click();
  await expect(page.getByText("Telegram · handoff")).toBeVisible();
  await expect(page.getByRole("button", { name: /Take over/ })).toBeVisible();

  // Instagram: filtered to its own conversation, tagged with the Instagram platform.
  await tabs.getByRole("tab", { name: /Instagram/ }).click();
  await expect(page.getByRole("button", { name: /Aadesh S on Telegram/ })).toHaveCount(0);
  const igRow = page.getByRole("button", { name: new RegExp(`${IGSID} on Instagram`) });
  await expect(igRow).toBeVisible();
  await igRow.click();
  await expect(page.getByText("Instagram · handoff")).toBeVisible();
});
