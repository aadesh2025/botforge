import { test, expect } from "@playwright/test";
import { API, auth, authenticateBrowser, createAccount } from "./helpers";

// Team performance reports on people, not channels — derived from Handoff.assigned_to and
// operator messages, both of which already existed.
test("team performance reports a teammate's handled, replied and closed counts", async ({
  page,
  context,
  request,
}) => {
  const account = await createAccount(request, "Team Perf Org");
  const agent = await (
    await request.post(`${API}/v1/agents`, { headers: auth(account), data: { name: "Perf Bot" } })
  ).json();
  await request.patch(`${API}/v1/agents/${agent.id}/versions/1`, {
    headers: auth(account),
    data: {
      fallback_message: "Connecting you to a teammate now.",
      features: { tools_enabled: false, memory_enabled: true, handoff_enabled: true },
    },
  });

  // One handoff taken over, replied to and closed.
  const chat = await request.post(`${API}/v1/public/agents/${agent.public_key}/chat`, {
    data: { message: "I want a human agent", stream: false },
  });
  const cid = (await chat.json()).conversation_id;
  await request.post(`${API}/v1/inbox/conversations/${cid}/takeover`, { headers: auth(account) });
  await request.post(`${API}/v1/inbox/conversations/${cid}/messages`, {
    headers: auth(account),
    data: { text: "On it — one moment." },
  });
  await request.post(`${API}/v1/inbox/conversations/${cid}/close`, { headers: auth(account) });

  await authenticateBrowser(context, account);
  await page.goto("/analytics");

  const section = page.getByRole("region", { name: "Team performance" });
  await expect(section).toBeVisible();

  // helpers.createAccount signs up with full_name "E2E User".
  const row = section.getByRole("row", { name: /E2E User/ });
  await expect(row).toBeVisible();
  await expect(row.getByText("1", { exact: true }).first()).toBeVisible();

  const text = (await section.textContent()) ?? "";
  expect(text).not.toContain("NaN");
  expect(text).not.toContain("undefined");
});

test("an untouched handoff queue shows a prompt, not an empty table", async ({
  page,
  context,
  request,
}) => {
  const account = await createAccount(request, "Team Empty Org");
  await authenticateBrowser(context, account);
  await page.goto("/analytics");

  const section = page.getByRole("region", { name: "Team performance" });
  await expect(section.getByText(/No handoffs have been taken over yet/)).toBeVisible();
});
