import { test, expect } from "@playwright/test";
import { API, auth, createAccount, createPublishedAgent } from "./helpers";

// A builder edit (new launcher design + color) must reflect on an already-embedded widget on the
// next page load — the <script> tag is never re-pasted (config is live-fetched from the API).
async function embed(page: import("@playwright/test").Page, publicKey: string) {
  await page.goto("/login");
  await page.evaluate(
    ([key, api]) => {
      const s = document.createElement("script");
      s.src = "/widget.js";
      s.setAttribute("data-agent", key);
      s.setAttribute("data-api", api);
      document.body.appendChild(s);
    },
    [publicKey, API],
  );
  await expect(page.locator(".bf-launcher")).toBeVisible({ timeout: 15_000 });
}

test("criterion: widget customization reflects on a live embed without re-pasting the script", async ({ page, request }) => {
  const account = await createAccount(request, "Widget Style Org");
  const { id, publicKey } = await createPublishedAgent(request, account, { name: "Styled Bot" });

  // 1) Default look: the legacy text pill launcher, ember accent.
  await embed(page, publicKey);
  const launcher = page.locator(".bf-launcher");
  await expect(launcher).toHaveClass(/bf-pill/);
  const before = await launcher.evaluate((el) => getComputedStyle(el).backgroundColor);

  // 2) "Builder save": change launcher design + accent color, then publish (branch-on-edit).
  const detail = await (await request.get(`${API}/v1/agents/${id}`, { headers: auth(account) })).json();
  const patched = await request.patch(`${API}/v1/agents/${id}/versions/${detail.draft_version}`, {
    headers: auth(account),
    data: { persona: { widget: { primaryColor: "#00AAFF", floatingButtonStyle: "circle-message" } } },
  });
  expect(patched.ok(), await patched.text()).toBeTruthy();
  const newVersion = (await patched.json()).version;
  const pub = await request.post(`${API}/v1/agents/${id}/versions/${newVersion}/publish`, { headers: auth(account) });
  expect(pub.ok(), await pub.text()).toBeTruthy();

  // 3) Same embed, fresh page load → the new design + color are live.
  await embed(page, publicKey);
  await expect(launcher).not.toHaveClass(/bf-pill/); // circle, not pill
  await expect(launcher.locator("svg")).toBeVisible(); // message icon
  const after = await launcher.evaluate((el) => getComputedStyle(el).backgroundColor);
  expect(after).toBe("rgb(0, 170, 255)");
  expect(after).not.toBe(before);
});

async function post(page: import("@playwright/test").Page, theme: Record<string, unknown>) {
  await page.evaluate((t) => {
    window.postMessage(
      { type: "bf-preview-config", config: { name: "Preview Bot", welcome_message: "Hi", suggested_prompts: [], theme: t } },
      "*",
    );
  }, theme);
}

test("builder preview: config changes apply live and NEVER change the open/closed state", async ({ page }) => {
  await page.goto("/widget-preview.html");
  const launcher = page.locator(".bf-launcher");
  const panel = page.locator(".bf-panel");
  await expect(launcher).toBeVisible({ timeout: 10_000 });

  // Preview starts CLOSED, like a real embed (the reported bug was it force-opening).
  await expect(panel).not.toHaveClass(/bf-show/);

  // A config change (color + design) applies live but must NOT open the panel.
  await post(page, { primary_color: "#22CC88", floating_button_style: "rounded-square", mode: "dark" });
  await expect.poll(() => launcher.evaluate((el) => getComputedStyle(el).backgroundColor)).toBe("rgb(34, 204, 136)");
  await expect(launcher).toHaveClass(/bf-square/); // design applied while closed
  await expect(panel).not.toHaveClass(/bf-show/); // still closed — the bug is fixed

  // Another change (simulating a keystroke on a different control) also stays closed.
  await post(page, { primary_color: "#FF0000", floating_button_style: "circle-dots", mode: "dark" });
  await expect(panel).not.toHaveClass(/bf-show/);

  // Once the user opens it, subsequent config changes must keep it OPEN.
  await launcher.click();
  await expect(panel).toHaveClass(/bf-show/);
  await post(page, { primary_color: "#0000FF", floating_button_style: "circle-chat", mode: "dark" });
  await expect(panel).toHaveClass(/bf-show/); // stayed open
});

test("mobile: an open panel hides the launcher below 768px, keeps it above", async ({ page }) => {
  // Phone-width viewport: the fullscreen panel would otherwise paint over the equal-z-index
  // launcher and swallow clicks meant for the send button.
  await page.setViewportSize({ width: 400, height: 720 });
  await page.goto("/widget-preview.html");
  const launcher = page.locator(".bf-launcher");
  const closeBtn = page.locator(".bf-x");
  await expect(launcher).toBeVisible({ timeout: 10_000 }); // visible while closed

  await launcher.click(); // open
  await expect(launcher).toBeHidden(); // hidden while open at phone width
  await expect(closeBtn).toBeVisible(); // the panel's own close button is the control
  await closeBtn.click();
  await expect(launcher).toBeVisible(); // reappears once closed

  // Desktop width: the launcher stays visible while open and doubles as the close control.
  await page.setViewportSize({ width: 1100, height: 800 });
  await launcher.click(); // open
  await expect(launcher).toBeVisible();
  await launcher.click(); // launcher acts as close
  await expect(page.locator(".bf-panel")).not.toHaveClass(/bf-show/);
});

test("transparent style: header has no solid backdrop", async ({ page }) => {
  await page.goto("/widget-preview.html");
  await expect(page.locator(".bf-launcher")).toBeVisible({ timeout: 10_000 });
  await page.locator(".bf-launcher").click(); // open so the header is rendered
  await post(page, { primary_color: "#E8590C", widget_style: "transparent", mode: "light" });
  const headBg = await page.locator(".bf-head").evaluate((el) => getComputedStyle(el).backgroundColor);
  // No accent-colored bar — transparent (or fully transparent rgba), never the solid accent.
  expect(headBg === "rgba(0, 0, 0, 0)" || headBg === "transparent").toBeTruthy();
});
