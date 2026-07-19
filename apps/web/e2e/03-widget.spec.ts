import { test, expect } from "@playwright/test";
import { API, createAccount, createPublishedAgent } from "./helpers";

// PRD acceptance criterion 3: embed the widget on a plain page and chat through it.
// We host it on the web origin (so the public API's CORS allows the fetch) and inject the
// widget <script> exactly as a site owner would, using the agent's real public key.
test("criterion 3: embedded widget streams a reply", async ({ page, request }) => {
  const account = await createAccount(request, "Widget Org");
  const { publicKey } = await createPublishedAgent(request, account, { name: "Widget Bot" });

  // A public page on the web origin acts as the "customer site".
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

  // Launcher mounts (Shadow-DOM isolated; Playwright pierces open shadow roots).
  const launcher = page.locator(".bf-launcher");
  await expect(launcher).toBeVisible({ timeout: 15_000 });
  await launcher.click();

  // Send a message through the widget composer.
  const composer = page.locator(".bf-ta");
  await composer.fill("Hello widget");
  await page.locator(".bf-send").click();

  // The bot bubble streams back the deterministic echo.
  await expect(page.locator(".bf-bot .bf-bubble").last()).toContainText(/echo:\s*Hello widget/i, {
    timeout: 20_000,
  });
});
