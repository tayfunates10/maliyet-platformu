/** @type {import('next').NextConfig} */
const immutableWidgetHeaders = [
  { key: "Access-Control-Allow-Origin", value: "*" },
  { key: "Cross-Origin-Resource-Policy", value: "cross-origin" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Cache-Control", value: "public, max-age=31536000, immutable" },
];

const nextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  async headers() {
    return [
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
    ];
  },
  experimental: {
    useTypeScriptCli: true,
  },
};

export default nextConfig;
