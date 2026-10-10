import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // the game ships a browser-only renderer; nothing here needs SSR
  experimental: { optimizePackageImports: ["lucide-react"] },
};

export default nextConfig;
