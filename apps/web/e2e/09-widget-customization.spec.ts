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

test("builder live preview: the real widget bundle applies posted config instantly", async ({ page }) => {
  // The builder embeds this page in an iframe and posts config via postMessage — no save round-trip.
  await page.goto("/widget-preview.html");
  // Wait until the widget has mounted (so its postMessage listener is registered).
  await expect(page.locator(".bf-launcher")).toBeVisible({ timeout: 10_000 });
  await page.evaluate(() => {
    window.postMessage(
      {
        type: "bf-preview-config",
        config: {
          name: "Preview Bot",
          welcome_message: "Hi from preview",
          suggested_prompts: [],
          theme: { primary_color: "#22CC88", floating_button_style: "rounded-square", mode: "dark" },
        },
      },
      "*",
    );
  });
  const launcher = page.locator(".bf-launcher");
  await expect(launcher).toBeVisible({ timeout: 10_000 });
  // The color applies live to the launcher (proves applyTheme ran from the posted config).
  await expect
    .poll(async () => launcher.evaluate((el) => getComputedStyle(el).backgroundColor))
    .toBe("rgb(34, 204, 136)");
  // Collapse the auto-opened panel so the launcher shows its chosen design (not the close button).
  await page.evaluate(() => (window as unknown as { BotForge?: { close: () => void } }).BotForge?.close());
  await expect(launcher).toHaveClass(/bf-square/); // rounded-square design applied live
});
