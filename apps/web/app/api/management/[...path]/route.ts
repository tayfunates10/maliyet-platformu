import { type NextRequest, NextResponse } from "next/server";
import { getPublicApiBaseUrl } from "@/lib/runtime-config";

const UUID = "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}";
const MAX_BODY_BYTES = 16_384;

type RouteRule = Readonly<{
  method: "GET" | "POST" | "PUT";
  pattern: RegExp;
  authenticated: boolean;
}>;

const ROUTE_RULES: readonly RouteRule[] = Object.freeze([
  { method: "POST", pattern: /^auth\/login$/, authenticated: false },
  { method: "GET", pattern: /^organizations$/, authenticated: true },
  {
    method: "GET",
    pattern: new RegExp(`^organizations/${UUID}/widget-branding-profiles$`),
    authenticated: true,
  },
  {
    method: "GET",
    pattern: new RegExp(`^organizations/${UUID}/widget-deployments$`),
    authenticated: true,
  },
  {
    method: "POST",
    pattern: new RegExp(`^organizations/${UUID}/widget-branding-profiles$`),
    authenticated: true,
  },
  {
    method: "PUT",
    pattern: new RegExp(`^organizations/${UUID}/widget-branding-profiles/${UUID}$`),
    authenticated: true,
  },
  {
    method: "POST",
    pattern: new RegExp(`^organizations/${UUID}/widget-deployments/${UUID}/presentation$`),
    authenticated: true,
  },
]);

function upstreamApiBase(): string {
  let parsed: URL;
  try {
    parsed = new URL(getPublicApiBaseUrl().trim());
  } catch {
    throw new Error("invalid upstream API base");
  }
  const hostname = parsed.hostname.toLowerCase();
  const loopback = hostname === "localhost" || hostname === "127.0.0.1" || hostname === "[::1]";
  const safeTransport = parsed.protocol === "https:" || (parsed.protocol === "http:" && loopback);
  if (
    !safeTransport ||
    parsed.username !== "" ||
    parsed.password !== "" ||
    parsed.search !== "" ||
    parsed.hash !== ""
  ) {
    throw new Error("invalid upstream API base");
  }
  parsed.pathname = parsed.pathname.replace(/\/+$/, "");
  return parsed.toString().replace(/\/$/, "");
}

function findRule(method: string, path: string): RouteRule | null {
  return ROUTE_RULES.find((rule) => rule.method === method && rule.pattern.test(path)) ?? null;
}

function genericJson(status: number, detail: string): NextResponse {
  return NextResponse.json(
    { detail },
    {
      status,
      headers: {
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
      },
    },
  );
}

async function proxy(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  const { path: pathParts } = await context.params;
  const path = pathParts.join("/");
  const rule = findRule(request.method, path);
  if (rule === null || request.nextUrl.search !== "") {
    return genericJson(404, "management route not found");
  }

  const authorization = request.headers.get("authorization");
  if (rule.authenticated) {
    if (
      authorization === null ||
      !authorization.startsWith("Bearer ") ||
      authorization.length < 23 ||
      authorization.length > 519
    ) {
      return genericJson(401, "authentication required");
    }
  } else if (authorization !== null) {
    return genericJson(400, "authorization not accepted on login");
  }

  let body: string | undefined;
  if (request.method === "POST" || request.method === "PUT") {
    body = await request.text();
    if (Buffer.byteLength(body, "utf8") > MAX_BODY_BYTES) {
      return genericJson(413, "request too large");
    }
    const contentType = request.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase();
    if (contentType !== "application/json") {
      return genericJson(415, "application/json required");
    }
  }

  let base: string;
  try {
    base = upstreamApiBase();
  } catch {
    return genericJson(503, "management upstream unavailable");
  }

  const headers = new Headers({ Accept: "application/json" });
  if (authorization !== null && rule.authenticated) headers.set("Authorization", authorization);
  if (body !== undefined) headers.set("Content-Type", "application/json");

  let upstream: Response;
  try {
    upstream = await fetch(`${base}/${path}`, {
      method: rule.method,
      headers,
      body,
      cache: "no-store",
      redirect: "error",
    });
  } catch {
    return genericJson(502, "management upstream request failed");
  }

  const responseContentType = upstream.headers.get("content-type")?.toLowerCase() ?? "";
  if (!responseContentType.includes("application/json")) {
    return genericJson(502, "management upstream returned invalid content");
  }
  const responseBody = await upstream.text();
  if (Buffer.byteLength(responseBody, "utf8") > 65_536) {
    return genericJson(502, "management upstream response too large");
  }
  return new NextResponse(responseBody, {
    status: upstream.status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

type RouteContext = Readonly<{
  params: Promise<{ path: string[] }>;
}>;

export function GET(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  return proxy(request, context);
}

export function POST(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  return proxy(request, context);
}

export function PUT(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  return proxy(request, context);
}
