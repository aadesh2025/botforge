import { expect, test } from "@playwright/test";
import { API, auth, authenticateBrowser, createAccount, createPublishedAgent } from "./helpers";

/** docs/17 Phase 2 gap-closure item 4: a Tool node's arguments become editable from the
 * properties panel, as raw JSON (see ADR-078). */

test("a tool node's arguments are editable as JSON and persist on save", async ({
  page,
  context,
  request,
}) => {
  const account = await createAccount(request, "Tool Args Org");
  const agent = await createPublishedAgent(request, account, { name: "Tool Args Agent" });

  // A real, agent-scoped HTTP tool so the properties panel's Tool dropdown has something to
  // offer — matches how the existing Tools tab creates one.
  const toolRes = await request.post(`${API}/v1/tools`, {
    headers: auth(account),
    data: {
      agent_id: agent.id, name: "lookup_order", type: "http",
      config: { method: "GET", url: "https://api.example.com/orders/{{order_id}}" },
    },
  });
  expect(toolRes.ok(), `create tool failed: ${toolRes.status()} ${await toolRes.text()}`).toBeTruthy();

  const createWf = await request.post(`${API}/v1/agents/${agent.id}/workflows`, {
    headers: auth(account),
    data: { name: "Tool args flow" },
  });
  const workflow = await createWf.json();

  await authenticateBrowser(context, account);
  await page.goto(`/agents/${agent.id}?tab=workflows`);
  await page.getByText("Tool args flow").click();
  await expect(page.getByRole("heading", { name: "Tool args flow" })).toBeVisible();

  const paletteTool = page.locator('[draggable="true"]', { hasText: "Tool" });
  const canvasSurface = page.locator(".react-flow__pane");
  await paletteTool.dragTo(canvasSurface, { targetPosition: { x: 350, y: 220 } });
  const toolNode = page.locator('[data-testid^="rf__node-tool_"]');
  await expect(toolNode).toBeVisible();
  await toolNode.click();

  // Pick the tool, then edit its arguments as JSON.
  await page.getByText("Select a tool…").click();
  await page.getByRole("option", { name: "lookup_order" }).click();

  const argsField = page.getByPlaceholder('{"query": "{{search_term}}"}');
  await argsField.fill("not valid json");
  await expect(page.getByText(/Invalid JSON/)).toBeVisible();

  await argsField.fill('{"order_id": "{{order_id}}", "limit": 5}');
  await expect(page.getByText(/Invalid JSON/)).toHaveCount(0);

  await page.getByRole("button", { name: /Save draft/ }).click();
  await expect(page.getByText(/Saved as draft v1/)).toBeVisible({ timeout: 10_000 });

  const versionsRes = await request.get(`${API}/v1/workflows/${workflow.id}/versions`, {
    headers: auth(account),
  });
  const versions = (await versionsRes.json()) as { graph: { nodes: { type: string; config: Record<string, unknown> }[] } }[];
  const toolNodeJson = versions[0].graph.nodes.find((n) => n.type === "tool");
  expect(toolNodeJson?.config.arguments).toEqual({ order_id: "{{order_id}}", limit: 5 });
});
