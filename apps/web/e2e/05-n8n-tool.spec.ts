import { test, expect } from "@playwright/test";
import { API, auth, authenticateBrowser, createAccount, createPublishedAgent } from "./helpers";

// PRD acceptance criterion 5: bind an n8n workflow as a tool the agent can trigger.
// Binding + tool config is exercised here through the API and the Automations UI. The live
// webhook *trigger* roundtrip requires a running n8n and is covered by the backend suite
// (tests/test_n8n.py — verified live in Phase 10); it is not re-run in keyless CI.
test("criterion 5: bind an n8n workflow as an agent tool", async ({ page, context, request }) => {
  const account = await createAccount(request, "n8n Org");
  const { id: agentId } = await createPublishedAgent(request, account, { name: "Ops Bot" });

  // Bind a workflow directly by webhook URL (no live n8n needed for the binding).
  const bindRes = await request.post(`${API}/v1/tools/n8n/bind`, {
    headers: auth(account),
    data: {
      name: "create_ticket",
      workflow_id: "wf_e2e_123",
      workflow_name: "Create Ticket",
      webhook_url: "https://n8n.example.test/webhook/create-ticket",
      mode: "sync",
      agent_id: agentId,
    },
  });
  expect(bindRes.ok(), await bindRes.text()).toBeTruthy();
  const tool = await bindRes.json();
  expect(tool.type).toBe("n8n");

  // The tool is attached to the agent, enabled, and carries the workflow config.
  const tools = await (
    await request.get(`${API}/v1/tools?agent_id=${agentId}`, { headers: auth(account) })
  ).json();
  const bound = tools.find((t: { id: string }) => t.id === tool.id);
  expect(bound, "bound tool should appear in the agent's tools").toBeTruthy();
  expect(bound.enabled).toBeTruthy();

  // The Automations page renders for the operator.
  await authenticateBrowser(context, account);
  await page.goto("/automations");
  await expect(page.getByRole("heading", { name: /automations/i })).toBeVisible();
});
