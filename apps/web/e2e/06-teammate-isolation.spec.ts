import { test, expect } from "@playwright/test";
import { API, auth, createAccount, uniqueEmail } from "./helpers";

// PRD acceptance criterion 6: a teammate invited with a role sees only that org's data.
test("criterion 6: invited viewer sees only their org's data + read-only RBAC", async ({ page, context, request }) => {
  // Owner A with an agent in org A.
  const owner = await createAccount(request, "Org A");
  await request.post(`${API}/v1/agents`, { headers: auth(owner), data: { name: "Isolation Agent A" } });

  // A separate tenant, org B, with its own agent that org A must never see.
  const other = await createAccount(request, "Org B");
  await request.post(`${API}/v1/agents`, { headers: auth(other), data: { name: "Hidden Agent B" } });

  // Owner A invites a brand-new teammate as a viewer.
  const teammateEmail = uniqueEmail("mate");
  const inviteRes = await request.post(`${API}/v1/orgs/${owner.orgId}/invitations`, {
    headers: auth(owner),
    data: { email: teammateEmail, role: "viewer" },
  });
  expect(inviteRes.ok(), await inviteRes.text()).toBeTruthy();
  const invite = await inviteRes.json();
  expect(invite.accept_token, "dev/CI should expose the accept token").toBeTruthy();

  // The teammate signs up and accepts the invitation.
  const signup = await request.post(`${API}/v1/auth/signup`, {
    data: { email: teammateEmail, password: "e2e-Password-123", full_name: "Teammate" },
  });
  const mateAuth = await signup.json();
  const accept = await request.post(`${API}/v1/orgs/invitations/${invite.accept_token}/accept`, {
    headers: { Authorization: `Bearer ${mateAuth.access_token}` },
  });
  expect(accept.ok(), await accept.text()).toBeTruthy();

  const mateInOrgA = { Authorization: `Bearer ${mateAuth.access_token}`, "X-Org-Id": owner.orgId };

  // Isolation: scoped to org A the teammate sees Agent A but never org B's agent.
  const agentsInA = await (await request.get(`${API}/v1/agents`, { headers: mateInOrgA })).json();
  const namesInA = agentsInA.map((a: { name: string }) => a.name);
  expect(namesInA).toContain("Isolation Agent A");
  expect(namesInA).not.toContain("Hidden Agent B");

  // RBAC: a viewer cannot create agents.
  const forbidden = await request.post(`${API}/v1/agents`, {
    headers: mateInOrgA,
    data: { name: "Nope" },
  });
  expect(forbidden.status()).toBe(403);

  // In the browser, sign the teammate in scoped to org A, and confirm they see Agent A only.
  const web = new URL(process.env.E2E_WEB_URL ?? "http://localhost:3001");
  await context.addCookies([
    { name: "bf_access", value: mateAuth.access_token, domain: web.hostname, path: "/", sameSite: "Lax" },
    { name: "bf_refresh", value: mateAuth.refresh_token, domain: web.hostname, path: "/", sameSite: "Lax" },
    { name: "bf_org", value: owner.orgId, domain: web.hostname, path: "/", sameSite: "Lax" },
  ]);
  await page.goto("/agents");
  await expect(page.getByText("Isolation Agent A")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("Hidden Agent B")).toHaveCount(0);
});
