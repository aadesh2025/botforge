#!/usr/bin/env node
/**
 * Run the Playwright suite, then always sweep the scratch data it created.
 *
 *     npm run test:e2e            # from apps/web
 *     npm run test:e2e -- --ui    # extra args pass straight through
 *
 * **Why this wrapper exists.** `playwright.config.ts` sets no `DATABASE_URL`, so the E2E suite
 * signs real users up against the same Postgres the dev app and the Admin console are pointed
 * at. That is deliberate — the tests exercise real flows rather than mocks — but it means every
 * run leaves its fixtures behind ("A11y Widget Org", "Bad Token Org", "Sidebar Org", …), and
 * they pile up in the Admin console next to real client orgs. One run left 118 scratch orgs
 * against 7 real ones.
 *
 * `app/db/cleanup_devdata.py` already knew how to remove them; nothing ran it automatically.
 *
 * Two properties matter and both are easy to get wrong:
 *
 * 1. **Cleanup runs whether the suite passed or failed.** A failed run leaves *more* debris than
 *    a passing one, so skipping cleanup on failure would sweep exactly the case that needs it.
 * 2. **The suite's exit code is preserved.** Cleanup must never turn a red run green — CI reads
 *    this exit code. A cleanup failure is reported loudly but does not overwrite a test failure.
 */

import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const WEB = resolve(ROOT, "apps/web");
const API = resolve(ROOT, "apps/api");

/** Run a command to completion; resolve with its exit code rather than throwing. */
function run(command, args, cwd) {
  return new Promise((resolvePromise) => {
    const child = spawn(command, args, { cwd, stdio: "inherit", shell: true });
    child.on("close", (code) => resolvePromise(code ?? 1));
    child.on("error", () => resolvePromise(1));
  });
}

/** The cleanup entry point, preferring the same runner the Makefile uses. */
async function cleanup() {
  // `uv run` matches `make clean-devdata`; fall back to the venv interpreter so a machine
  // without uv on PATH still gets swept rather than silently skipping it.
  const viaUv = await run("uv", ["run", "python", "-m", "app.db.cleanup_devdata"], API);
  if (viaUv === 0) return 0;
  const python =
    process.platform === "win32" ? ".venv\\Scripts\\python.exe" : ".venv/bin/python";
  return run(python, ["-m", "app.db.cleanup_devdata"], API);
}

const passthrough = process.argv.slice(2);
const testCode = await run("npx", ["playwright", "test", ...passthrough], WEB);

console.log(
  `\n[e2e] suite exited ${testCode} — sweeping @example.com fixtures it created...`,
);
const cleanCode = await cleanup();
if (cleanCode !== 0) {
  // Loud, but never fatal to the run: a dirty database is a nuisance, a masked test result
  // is a lie.
  console.error(
    "[e2e] cleanup FAILED. Scratch orgs are still in the database — run `make clean-devdata`.",
  );
} else {
  console.log("[e2e] cleanup done — Admin console shows real orgs only.");
}

// Deliberately the *test* code, not the cleanup code.
process.exit(testCode);
