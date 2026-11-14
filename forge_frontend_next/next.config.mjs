/** @type {import('next').NextConfig} */
const backend = process.env.FORGE_BACKEND_URL || "http://127.0.0.1:8010";
const basePath = (process.env.NEXT_PUBLIC_BASE_PATH || "").trim().replace(/\/+$/, "");

const nextConfig = {
  transpilePackages: ["@narrativeos/ui"],
  reactStrictMode: true,
  experimental: { proxyTimeout: 150000 },
  distDir: process.env.FORGE_NEXT_DIST_DIR || ".next",
  basePath: basePath || undefined,
  trailingSlash: true,
  skipTrailingSlashRedirect: true,
  // Preserve links issued before public works switched to canonical trailing slashes.
  async redirects() {
    return [{
      source: "/practice/works/:workId([0-9a-f]{32})",
      destination: "/practice/works/:workId/",
      permanent: false,
    }];
  },
  async rewrites() {
    return [
      { source: "/api/forge/community", destination: `${backend}/community` },
      { source: "/api/forge/community/:path*", destination: `${backend}/community/:path*` },
      { source: "/api/forge/health", destination: `${backend}/health` },
      { source: "/api/forge/admin/:path*", destination: `${backend}/admin/:path*` },
      { source: "/api/forge/auth/me", destination: `${backend}/auth/me` },
      { source: "/api/forge/auth/config", destination: `${backend}/auth/config` },
      { source: "/api/forge/nar-agent/:path*", destination: `${backend}/nar-agent/:path*` },
      // Saved private works and explicit public snapshots are different API surfaces.
      { source: "/api/forge/works", destination: `${backend}/works` },
      { source: "/api/forge/works/:path*", destination: `${backend}/works/:path*` },
      { source: "/api/forge/public/works", destination: `${backend}/public/works` },
      { source: "/api/forge/public/works/:path*", destination: `${backend}/public/works/:path*` },
      { source: "/api/forge/credits/balance", destination: `${backend}/credits/balance` },
      { source: "/api/forge/payments/:path*", destination: `${backend}/payments/:path*` },
      { source: "/api/forge/assets", destination: `${backend}/assets` },
      { source: "/api/forge/assets/:path*", destination: `${backend}/assets/:path*` },
      { source: "/api/forge/jobs", destination: `${backend}/jobs` },
      { source: "/api/forge/jobs/:path*", destination: `${backend}/jobs/:path*` },
      { source: "/api/forge/public/jobs/:path*", destination: `${backend}/public/jobs/:path*` },
      { source: "/api/forge/quiz/:path*", destination: `${backend}/quiz/:path*` },
      { source: "/api/forge/public/quiz/:path*", destination: `${backend}/public/quiz/:path*` },
      { source: "/api/forge/generation-options/:path*", destination: `${backend}/generation-options/:path*` },
      { source: "/play/:path*", destination: `${backend}/play/:path*` }
    ];
  }
};

export default nextConfig;
