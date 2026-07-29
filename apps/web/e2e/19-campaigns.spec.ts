import { test, expect } from "@playwright/test";
import { API, auth, authenticateBrowser, createAccount } from "./helpers";

// A proactive campaign opens the widget unprompted after a delay. No external channel,
// so no consent question — the visitor is already on the site. Outbound broadcasts are a
// different feature and deliberately cannot be switched on yet (ADR-039).

test("a widget campaign is created in the builder and reaches the public config", async ({
  page,
  context,
  request,
}) => {
  const account = await createAccount(request, "Campaign Org");
  const agent = await (
    await request.post(`${API}/v1/agents`, { headers: auth(account), data: { name: "Campaign Bot" } })
  ).json();

  await authenticateBrowser(context, account);
  await page.goto(`/agents/${agent.id}?tab=channels`);

  await page.getByLabel("Name", { exact: true }).fill("Pricing nudge");
  await page.getByLabel("Message", { exact: true }).fill("Questions about pricing? I can help.");
  await page.getByLabel("Show after (seconds)").fill("5");
  await page.getByLabel("Only on URLs containing (optional)").fill("/pricing");
  await page.getByRole("button", { name: "Add campaign" }).click();

  const list = page.getByRole("list", { name: "Campaigns" });
  await expect(list.getByText("Pricing nudge")).toBeVisible();
  // Created as a draft, so it isn't live until someone says so.
  await expect(list.getByText("draft")).toBeVisible();

  // Drafts stay off the widget.
  let config = await (await request.get(`${API}/v1/public/agents/${agent.public_key}/config`)).json();
  expect(config.campaigns).toEqual([]);

  await list.getByRole("button", { name: "Activate" }).click();
  await expect(list.getByText("active")).toBeVisible();

  config = await (await request.get(`${API}/v1/public/agents/${agent.public_key}/config`)).json();
  expect(config.campaigns).toHaveLength(1);
  expect(config.campaigns[0].message).toBe("Questions about pricing? I can help.");
  expect(config.campaigns[0].delay_seconds).toBe(5);
  expect(config.campaigns[0].url_pattern).toBe("/pricing");
});

test("the widget shows an active campaign unprompted after its delay", async ({ page, request }) => {
  const account = await createAccount(request, "Campaign Widget Org");
  const agent = await (
    await request.post(`${API}/v1/agents`, { headers: auth(account), data: { name: "Proactive Bot" } })
  ).json();
  await request.post(`${API}/v1/campaigns`, {
    headers: auth(account),
    data: {
      agent_id: agent.id,
      kind: "widget_trigger",
      name: "Quick hello",
      message: "Need a hand with anything?",
      trigger_config: { delay_seconds: 3 },
      status: "active",
    },
  });

  // Embed the real widget on a page of the web origin, exactly as a site owner would.
  await page.goto("/login");
  await page.evaluate(
    ([key, api]) => {
      const s = document.createElement("script");
      s.src = "/widget.js";
      s.setAttribute("data-agent", key);
      s.setAttribute("data-api", api);
      document.body.appendChild(s);
    },
    [agent.public_key, API],
  );

  // The launcher mounts closed — nothing has fired yet.
  await expect(page.locator(".bf-launcher")).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".bf-panel.bf-open")).toHaveCount(0);

  // …then the campaign opens the panel itself and shows its message.
  await expect(page.getByText("Need a hand with anything?")).toBeVisible({ timeout: 15_000 });
});

test("an outbound broadcast can be drafted but not activated", async ({ request }) => {
  const account = await createAccount(request, "Broadcast Org");
  const agent = await (
    await request.post(`${API}/v1/agents`, { headers: auth(account), data: { name: "Blast Bot" } })
  ).json();

  const draft = await request.post(`${API}/v1/campaigns`, {
    headers: auth(account),
    data: { agent_id: agent.id, kind: "broadcast", name: "Spring sale", message: "20% off" },
  });
  expect(draft.status()).toBe(201);

  const activate = await request.patch(`${API}/v1/campaigns/${(await draft.json()).id}`, {
    headers: auth(account),
    data: { status: "active" },
  });
  expect(activate.status()).toBe(400);
  expect((await activate.json()).error.code).toBe("campaigns.broadcast_disabled");
});
