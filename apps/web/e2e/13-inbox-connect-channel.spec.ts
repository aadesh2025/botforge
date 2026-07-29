import { test, expect } from "@playwright/test";
import { API, auth, authenticateBrowser, createAccount } from "./helpers";

// The Inbox now shows a tab for every channel, so an operator can discover a platform
// they haven't set up — and get to the credential form from there, rather than having to
// already know the builder's Channels tab exists. The form itself is not duplicated: the
// Inbox only routes to it with the right agent and channel type pre-selected.
test("connecting an unconnected channel from the Inbox opens the builder's connect dialog", async ({
  page,
  context,
  request,
}) => {
  const account = await createAccount(request, "Connect Flow Org");

  // Exactly one agent, so there's no ambiguity about which one gets the channel.
  const create = await request.post(`${API}/v1/agents`, {
    headers: auth(account),
    data: { name: "Only Agent" },
  });
  expect(create.ok(), await create.text()).toBeTruthy();
  const agent = await create.json();

  await authenticateBrowser(context, account);
  await page.goto("/inbox");
  await expect(page.getByRole("heading", { name: /inbox/i })).toBeVisible();

  const tabs = page.getByRole("tablist", { name: "Channels" });

  // Nothing is connected, yet every channel is present and marked as such.
  for (const label of ["Messenger", "Instagram", "WhatsApp", "Telegram", "Slack", "Discord"]) {
    await expect(tabs.getByRole("tab", { name: `${label} (not connected)` })).toBeVisible();
  }
  // Web Chat is inherent to every agent — never flagged.
  await expect(tabs.getByRole("tab", { name: "Web Chat", exact: true })).toBeVisible();

  await tabs.getByRole("tab", { name: "WhatsApp (not connected)" }).click();

  // Both panels explain the situation, distinctly from an ordinary empty inbox.
  await expect(page.getByText("WhatsApp isn’t connected yet.").first()).toBeVisible();
  await expect(page.getByText("Nothing in the inbox yet.")).toHaveCount(0);

  await page.getByRole("button", { name: "Connect WhatsApp" }).click();

  // Landed on that agent's builder, Channels tab, with the WhatsApp form already open.
  await expect(page).toHaveURL(new RegExp(`/agents/${agent.id}\\?tab=channels`));
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("Connect WhatsApp (Meta)")).toBeVisible();
  // The real credential fields — one implementation, reached from two places.
  await expect(dialog.getByText("Phone number ID")).toBeVisible();
  await expect(dialog.getByText("App secret")).toBeVisible();

  // The param is consumed, so a reload doesn't reopen the dialog unprompted.
  await expect(page).not.toHaveURL(/connect=/);
  await page.reload();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("a connected channel shows its inbox, not the connect prompt", async ({ page, context, request }) => {
  const account = await createAccount(request, "Connected Channel Org");
  const agent = await (
    await request.post(`${API}/v1/agents`, { headers: auth(account), data: { name: "Agent" } })
  ).json();

  const ch = await (
    await request.post(`${API}/v1/channels`, {
      headers: auth(account),
      data: { agent_id: agent.id, type: "telegram", config: { bot_token: "123:E2E" } },
    })
  ).json();
  await request.post(`${API}/v1/channels/${ch.id}/enable`, { headers: auth(account) });

  await authenticateBrowser(context, account);
  await page.goto("/inbox");

  const tabs = page.getByRole("tablist", { name: "Channels" });
  // A just-connected channel also carries the "New" badge, so match the label plus that.
  await tabs.getByRole("tab", { name: /^Telegram( New)?$/ }).click();

  // Connected but no messages yet — the ordinary empty state, never the setup prompt.
  await expect(page.getByText("Nothing in the inbox yet.")).toBeVisible();
  await expect(page.getByText(/isn’t connected yet/)).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Connect Telegram$/ })).toHaveCount(0);
});
