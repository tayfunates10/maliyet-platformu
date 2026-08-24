/** @type {import('next').NextConfig} */
const immutableWidgetHeaders = [
  { key: "Access-Control-Allow-Origin", value: "*" },
  { key: "Cross-Origin-Resource-Policy", value: "cross-origin" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Cache-Control", value: "public, max-age=31536000, immutable" },
];

const applicationSecurityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "no-referrer" },
  { key: "X-Frame-Options", value: "DENY" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
  },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  { key: "Cross-Origin-Resource-Policy", value: "same-origin" },
  { key: "X-Permitted-Cross-Domain-Policies", value: "none" },
];

const nextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  output: "standalone",
  async headers() {
    return [
      {
        source: "/((?!widget/).*)",
        headers: applicationSecurityHeaders,
      },
      {
        source: "/widget/v1.0.0/loader.js",
        headers: immutableWidgetHeaders,
      },
      {
        source: "/widget/v1.1.0/loader.js",
        headers: immutableWidgetHeaders,
      },
      {
        source: "/widget/v1.1.0/styles.css",
        headers: immutableWidgetHeaders,
      },
      {
        source: "/widget/v1.2.0/loader.js",
        headers: immutableWidgetHeaders,
      },
      {
        source: "/widget/v1.2.0/styles.css",
        headers: immutableWidgetHeaders,
      },
    ];
  },
  experimental: {
    useTypeScriptCli: true,
  },
};

export default nextConfig;
