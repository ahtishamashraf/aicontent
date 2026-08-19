import type { NextConfig } from "next";

/**
 * Security headers are also set by the API for its own responses; these cover
 * the pages the browser loads directly.
 *
 * The CSP omits 'unsafe-eval' and allows inline styles only, which Tailwind's
 * build output and Next's style injection require. Scripts are restricted to
 * same-origin plus the nonce-less inline bootstrap Next emits, so no third
 * party can inject executable code.
 */
const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  {
    key: "Permissions-Policy",
    value: "geolocation=(), microphone=(), camera=(), payment=(), usb=()",
  },
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      // Next's runtime injects an inline bootstrap script.
      "script-src 'self' 'unsafe-inline'",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data:",
      "font-src 'self'",
      // Same-origin API only. No third-party endpoint may be contacted.
      "connect-src 'self'",
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self'",
      "object-src 'none'",
    ].join("; "),
  },
];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  output: "standalone",
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
  async rewrites() {
    // Same-origin proxy to the API so cookies stay host-only and no CORS
    // preflight is needed in the browser.
    const target = process.env.API_INTERNAL_URL ?? "http://localhost:8000";
    return [{ source: "/api/v1/:path*", destination: `${target}/api/v1/:path*` }];
  },
};

export default nextConfig;
