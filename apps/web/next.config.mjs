/** @type {import("next").NextConfig} */
// NEXT_OUTPUT=standalone is set by apps/web/Dockerfile; local `next start` keeps the default output.
const nextConfig = { reactStrictMode: true, poweredByHeader: false, ...(process.env.NEXT_OUTPUT === "standalone" ? { output: "standalone" } : {}) };
export default nextConfig;
