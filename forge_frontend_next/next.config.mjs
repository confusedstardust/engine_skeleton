/** @type {import('next').NextConfig} */
const backend = process.env.FORGE_BACKEND_URL || "http://127.0.0.1:8010";

const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
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
