import type { NextConfig } from "next";

/**
 * Campus front end.
 *
 * Production is a fully static export ("output: 'export'") — no Node runtime.
 * Django/whitenoise serves the contents of ./out. All data comes from the
 * DRF API at /api (same origin behind Caddy in prod; proxied in dev).
 */
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true }, // no Next image server in a static export
  eslint: { ignoreDuringBuilds: false },
  typescript: { ignoreBuildErrors: false },
  async rewrites() {
    // dev only — static export ignores rewrites; prod is same-origin.
    return [
      {
        source: "/api/:path*",
        destination:
          (process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8001") +
          "/api/:path*",
      },
    ];
  },
};

export default nextConfig;
