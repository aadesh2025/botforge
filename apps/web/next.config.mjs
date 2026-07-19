import { fileURLToPath } from "url";

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Emit a self-contained server bundle for a small production image (infra/apps/web Dockerfile).
  output: "standalone",
  // Pin the workspace root to this app so Next/Turbopack never infers it from a stray
  // package-lock.json further up the tree (the repo root has no package.json).
  turbopack: {
    root: fileURLToPath(new URL(".", import.meta.url)),
  },
};

export default nextConfig;
