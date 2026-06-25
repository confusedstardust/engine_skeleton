/** @type {import('next').NextConfig} */
const backend = process.env.FORGE_BACKEND_URL || "http://127.0.0.1:8010";
const basePath = (process.env.NEXT_PUBLIC_BASE_PATH || "").trim().replace(/\/+$/, "");

const nextConfig = {
  reactStrictMode: true,
  basePath: basePath || undefined,
  async rewrites() {
    return [
      { source: "/api/forge/health", destination: `${backend}/health` },
      { source: "/api/forge/jobs", destination: `${backend}/jobs` },
      { source: "/api/forge/jobs/:path*", destination: `${backend}/jobs/:path*` },
      { source: "/api/forge/generation-options/:path*", destination: `${backend}/generation-options/:path*` },
      { source: "/play/:path*", destination: `${backend}/play/:path*` }
    ];
  }
};

export default nextConfig;
