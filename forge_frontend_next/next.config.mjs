/** @type {import('next').NextConfig} */
const backend = process.env.FORGE_BACKEND_URL || "http://127.0.0.1:8010";

const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  async rewrites() {
    return [
      { source: "/health", destination: `${backend}/health` },
      { source: "/jobs", destination: `${backend}/jobs` },
      { source: "/jobs/:path*", destination: `${backend}/jobs/:path*` },
      { source: "/play/:path*", destination: `${backend}/play/:path*` }
    ];
  }
};

export default nextConfig;
