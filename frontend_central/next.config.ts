import type { NextConfig } from "next";

/**
 * Campus Central front end -- a separate Next.js project from Campus's own
 * `frontend/` (see docs/CENTRAL_SYNC_SCOPE.md's C6 section for why: Central
 * is a genuinely separate product/database, not a new area of Campus).
 *
 * Production is a fully static export ("output: 'export'") -- no Node
 * runtime. Central's Django app (apps/central, a separate settings module/
 * database from Campus's own) serves the contents of ./out. All data comes
 * from the DRF API at /api/central/... (same origin behind Caddy in prod;
 * proxied in dev, same pattern as Campus's own frontend/next.config.ts).
 */
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  eslint: { ignoreDuringBuilds: false },
  typescript: { ignoreBuildErrors: false },
  async rewrites() {
    // dev only -- static export ignores rewrites; prod is same-origin.
    // Central's dev server defaults to :8002 (central/settings/dev.py),
    // distinct from Campus's own :8001.
    return [
      {
        source: "/api/:path*",
        destination:
          (process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8002") +
          "/api/:path*",
      },
    ];
  },
};

export default nextConfig;
