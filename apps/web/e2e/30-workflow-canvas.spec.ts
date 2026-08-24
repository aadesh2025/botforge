import { expect, test } from "@playwright/test";
import { API, auth, authenticateBrowser, createAccount, createPublishedAgent } from "./helpers";

/** The workflow canvas (docs/17 Phase 2 item 6): create a workflow, build a graph on the
 * canvas, save it as a draft, publish it, and run it — reading back the real server state at
 * each step rather than trusting only what's rendered. */

test("build, save, publish and test-run a workflow from the canvas", async ({ page, context, request }) => {
  const account = await createAccount(request, "Workflow Canvas Org");
  const agent = await createPublishedAgent(request, account, { name: "Canvas Agent" });

  await authenticateBrowser(context, account);
  await page.goto(`/agents/${agent.id}?tab=workflows`);

  await expect(page.getByRole("heading", { name: "Workflows" })).toBeVisible();
  await expect(page.getByText(/No workflows yet/)).toBeVisible();

  // Create a workflow through the dialog.
  await page.getByRole("button", { name: /New workflow/ }).click();
  await page.getByPlaceholder(/Refund approval/).fill("Greeting flow");
  await page.getByRole("button", { name: "Create workflow", exact: true }).click();

  // The canvas loads with its own default single Start node and toolbar.
  await expect(page.getByRole("heading", { name: "Greeting flow" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Save draft/ })).toBeVisible();
  await expect(page.getByText("Start", { exact: true })).toBeVisible();

  // Drag a Message node from the palette onto the canvas.
  const paletteMessage = page.locator('[draggable="true"]', { hasText: "Message" });
  const canvasSurface = page.locator(".react-flow__pane");
  await paletteMessage.dragTo(canvasSurface, { targetPosition: { x: 350, y: 220 } });
  const canvasMessageNode = page.locator('[data-testid^="rf__node-message"]');
  await expect(canvasMessageNode).toBeVisible();

  // Configure the new Message node via the properties panel.
  await canvasMessageNode.click();
  const contentField = page.getByPlaceholder("Hi {{user_name}}, ...");
  await expect(contentField).toBeVisible();
  await contentField.fill("Hello from the canvas!");

  // Save writes a real draft version to the server.
  await page.getByRole("button", { name: /Save draft/ }).click();
  await expect(page.getByText(/Saved as draft v1/)).toBeVisible({ timeout: 10_000 });

  const versionsRes = await request.get(`${API}/v1/agents/${agent.id}/workflows`, { headers: auth(account) });
  const [workflow] = (await versionsRes.json()) as { id: string }[];
  const versionsListRes = await request.get(`${API}/v1/workflows/${workflow.id}/versions`, {
    headers: auth(account),
  });
  const versions = (await versionsListRes.json()) as { version: number; graph: { nodes: { type: string }[] } }[];
  expect(versions).toHaveLength(1);
  // The canvas seeds a new workflow with start->end pre-wired (a bare start alone fails
  // validate_graph's "at least one end node" rule) — the dropped Message node adds a third.
  expect(versions[0].graph.nodes.map((n) => n.type).sort()).toEqual(["end", "message", "start"]);

  // Publish, then confirm the server actually marks it published.
  await page.getByRole("button", { name: "Publish", exact: true }).click();
  await expect(page.getByText(/v1 · published/)).toBeVisible({ timeout: 10_000 });
  const workflowRes = await request.get(`${API}/v1/workflows/${workflow.id}`, { headers: auth(account) });
  expect((await workflowRes.json()).current_version_id).toBeTruthy();

  // Test run: start -> end is reachable regardless of the disconnected Message node, so this
  // should genuinely complete — proving the run round-trips through the real dispatch/poll
  // path (create, enqueue-or-eager-execute, poll to a terminal status).
  await page.getByRole("button", { name: /Test run/ }).click();
  await expect(page.getByText(/Test run:/)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Test run: completed")).toBeVisible({ timeout: 15_000 });
});

test("a viewer sees the canvas read-only, with no palette or save controls", async ({ page, context, request }) => {
  const owner = await createAccount(request, "Canvas Owner Org");
  const viewer = await createAccount(request, "Canvas Viewer Org");
  const agent = await createPublishedAgent(request, owner, { name: "Viewer Canvas Agent" });

  const createWf = await request.post(`${API}/v1/agents/${agent.id}/workflows`, {
    headers: auth(owner),
    data: { name: "Owner's flow" },
  });
  const workflow = await createWf.json();

  const invite = await request.post(`${API}/v1/orgs/${owner.orgId}/invitations`, {
    headers: auth(owner),
    data: { email: viewer.email, role: "viewer" },
  });
  const token = (await invite.json()).accept_token as string;
  await request.post(`${API}/v1/orgs/invitations/${token}/accept`, {
    headers: { Authorization: `Bearer ${viewer.access}` },
  });

  await authenticateBrowser(context, { ...viewer, orgId: owner.orgId });
  await page.goto(`/agents/${agent.id}?tab=workflows`);

  await expect(page.getByText("Owner's flow")).toBeVisible();
  await expect(page.getByRole("button", { name: /New workflow/ })).toHaveCount(0);

  await page.getByText("Owner's flow").click();
  await expect(page.getByRole("heading", { name: "Owner's flow" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Save draft/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Test run/ })).toHaveCount(0);
  await expect(page.getByText("Nodes", { exact: true })).toHaveCount(0); // palette hidden

  // The server refuses too — hiding the controls is not access control.
  const denied = await request.post(`${API}/v1/workflows/${workflow.id}/versions`, {
    headers: { Authorization: `Bearer ${viewer.access}`, "X-Org-Id": owner.orgId },
    data: { graph: { nodes: [{ id: "s", type: "start" }], edges: [] } },
  });
  expect(denied.status()).toBe(403);
});
