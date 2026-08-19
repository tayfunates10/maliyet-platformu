const DEFAULT_API_BASE_URL = "http://localhost:8000";

export function getPublicApiBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  return configured && configured.length > 0 ? configured : DEFAULT_API_BASE_URL;
}
