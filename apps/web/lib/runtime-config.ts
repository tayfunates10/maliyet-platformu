const DEFAULT_DEVELOPMENT_API_BASE_URL = "http://localhost:8000";

function isLoopbackHostname(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "[::1]";
}

export function getPublicApiBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();

  if (!configured || configured.length === 0) {
    if (process.env.NODE_ENV === "production") {
      throw new Error("NEXT_PUBLIC_API_BASE_URL is required in production");
    }
    return DEFAULT_DEVELOPMENT_API_BASE_URL;
  }

  let url: URL;
  try {
    url = new URL(configured);
  } catch {
    throw new Error("NEXT_PUBLIC_API_BASE_URL must be an absolute URL");
  }

  if (url.username || url.password || url.search || url.hash) {
    throw new Error("NEXT_PUBLIC_API_BASE_URL must not contain credentials, query parameters, or fragments");
  }

  if (url.pathname !== "/") {
    throw new Error("NEXT_PUBLIC_API_BASE_URL must not contain a path");
  }

  if (url.protocol !== "https:") {
    const developmentLoopback = process.env.NODE_ENV !== "production" && url.protocol === "http:" && isLoopbackHostname(url.hostname);
    if (!developmentLoopback) {
      throw new Error("NEXT_PUBLIC_API_BASE_URL must use HTTPS outside local development");
    }
  }

  return url.origin;
}
