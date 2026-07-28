import path from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    // Playwright specs live in e2e/ and are run by `npm run test:e2e`.
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
  },
  // Vitest transforms with esbuild; the automatic runtime lets component tests use JSX
  // without importing React (tsconfig keeps `jsx: preserve` for Next's own build).
  esbuild: { jsx: "automatic" },
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
});
