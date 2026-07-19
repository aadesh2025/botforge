/** @type {import('next').NextConfig} */
const nextConfig = {
  // Emit a self-contained server bundle for a small production image (infra/apps/web Dockerfile).
  output: "standalone",
};

export default nextConfig;
