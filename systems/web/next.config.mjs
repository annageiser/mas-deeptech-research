/** @type {import('next').NextConfig} */
const nextConfig = {
  // Standalone output → small Docker runtime image (only the server + traced deps).
  output: "standalone",
  reactStrictMode: true,
  // The browser calls the API through the same origin under /api (Caddy proxies
  // /api/* → api container). Server components fetch via API_INTERNAL_URL.
  async rewrites() {
    const internal = process.env.API_INTERNAL_URL || "http://api:8000";
    return [{ source: "/api/:path*", destination: `${internal}/api/:path*` }];
  },
};
export default nextConfig;
