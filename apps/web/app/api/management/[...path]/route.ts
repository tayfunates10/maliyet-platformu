import { type NextRequest, NextResponse } from "next/server";
import { getServerApiBaseUrl } from "@/lib/runtime-config";

const UUID = "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}";
const ENGINE_KEY = "[a-z][a-z0-9_]{0,79}";
const VERSION = "[1-9][0-9]*";
const REPORT_FORMAT = "(?:csv|xlsx|docx|pdf)";
const MAX_BODY_BYTES = 16_384;
const MAX_REPORT_BYTES = 8 * 1024 * 1024;
const DEPLOYMENT_PAGE_LIMIT = 100;

type RouteRule = Readonly<{
  method: "GET" | "POST" | "PUT";
  pattern: RegExp;
  authenticated: boolean;
  responseKind?: "json" | "report";
  allowDeploymentPagination?: boolean;
  allowEmptyBody?: boolean;
}>;

const ROUTE_RULES: readonly RouteRule[] = Object.freeze([
  { method: "POST", pattern: /^auth\/login$/, authenticated: false },
  { method: "POST", pattern: /^auth\/logout$/, authenticated: true, allowEmptyBody: true },
  { method: "GET", pattern: /^organizations$/, authenticated: true, allowDeploymentPagination: true },
  { method: "GET", pattern: /^engines$/, authenticated: true },
  {
    method: "GET",
    pattern: new RegExp(`^organizations/${UUID}/dashboard$`),
    authenticated: true,
  },
  { method: "GET", pattern: new RegExp(`^engines/${ENGINE_KEY}$`), authenticated: true },
  {
    method: "GET",
    pattern: new RegExp(`^organizations/${UUID}/calculations$`),
    authenticated: true,
    allowDeploymentPagination: true,
  },
  {
    method: "POST",
    pattern: new RegExp(`^organizations/${UUID}/calculations$`),
    authenticated: true,
  },
  {
    method: "GET",
    pattern: new RegExp(`^organizations/${UUID}/calculations/${UUID}/versions$`),
    authenticated: true,
    allowDeploymentPagination: true,
  },
  {
    method: "GET",
    pattern: new RegExp(
      `^organizations/${UUID}/calculations/${UUID}/versions/${VERSION}/report\\.${REPORT_FORMAT}$`,
    ),
    authenticated: true,
    responseKind: "report",
  },
  {
    method: "POST",
    pattern: new RegExp(`^organizations/${UUID}/calculations/${UUID}/execute/${ENGINE_KEY}$`),
    authenticated: true,
  },
  {
    method: "POST",
    pattern: new RegExp(`^organizations/${UUID}/decision-analysis/investment-scenarios$`),
    authenticated: true,
  },
  {
    method: "GET",
    pattern: new RegExp(`^organizations/${UUID}/decision-analysis/investment-scenarios$`),
    authenticated: true,
    allowDeploymentPagination: true,
  },
  {
    method: "GET",
    pattern: new RegExp(`^organizations/${UUID}/decision-analysis/investment-scenarios/${UUID}$`),
    authenticated: true,
  },
  {
    method: "GET",
    pattern: new RegExp(`^organizations/${UUID}/widget-branding-profiles$`),
    authenticated: true,
  },
  {
    method: "GET",
    pattern: new RegExp(`^organizations/${UUID}/widget-deployments$`),
    authenticated: true,
    allowDeploymentPagination: true,
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

const REPORT_CONTENT_TYPES = Object.freeze([
  "text/csv",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/pdf",
]);

function upstreamApiBase(): string {
  let parsed: URL;
  try {
    parsed = new URL(getServerApiBaseUrl().trim());
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

function validatedQuery(request: NextRequest, rule: RouteRule): string | null {
  if (request.nextUrl.search === "") return "";
  if (!rule.allowDeploymentPagination) return null;
  const keys = [...request.nextUrl.searchParams.keys()];
  if (keys.some((key) => key !== "limit" && key !== "offset")) return null;
  if (keys.filter((key) => key === "limit").length > 1 || keys.filter((key) => key === "offset").length > 1) {
    return null;
  }
  const limitText = request.nextUrl.searchParams.get("limit");
  const offsetText = request.nextUrl.searchParams.get("offset");
  if (limitText === null || offsetText === null || !/^\d+$/.test(limitText) || !/^\d+$/.test(offsetText)) {
    return null;
  }
  const limit = Number(limitText);
  const offset = Number(offsetText);
  if (!Number.isSafeInteger(limit) || limit < 1 || limit > DEPLOYMENT_PAGE_LIMIT) return null;
  if (!Number.isSafeInteger(offset) || offset < 0) return null;
  return `?limit=${limit}&offset=${offset}`;
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

function safeContentDisposition(value: string | null): string | null {
  if (value === null || value.length > 240 || /[\r\n]/.test(value)) return null;
  return /^attachment; filename="[A-Za-z0-9._-]+"$/.test(value) ? value : null;
}

function declaredReportSize(upstream: Response): number | null {
  const raw = upstream.headers.get("content-length");
  if (raw === null || !/^\d+$/.test(raw)) return null;
  const size = Number(raw);
  return Number.isSafeInteger(size) ? size : null;
}

async function readBoundedReportBody(upstream: Response): Promise<Uint8Array | null> {
  const declaredSize = declaredReportSize(upstream);
  if (declaredSize !== null && declaredSize > MAX_REPORT_BYTES) {
    await upstream.body?.cancel();
    return null;
  }
  if (upstream.body === null) return new Uint8Array();

  const reader = upstream.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > MAX_REPORT_BYTES) {
        await reader.cancel();
        return null;
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }

  const body = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return body;
}

async function proxyReport(upstream: Response): Promise<NextResponse> {
  const contentType = upstream.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase() ?? "";
  if (!REPORT_CONTENT_TYPES.includes(contentType)) {
    await upstream.body?.cancel();
    return genericJson(502, "management upstream returned invalid report content");
  }
  const body = await readBoundedReportBody(upstream);
  if (body === null) return genericJson(502, "management upstream report too large");
  const responseBody = new ArrayBuffer(body.byteLength);
  new Uint8Array(responseBody).set(body);
  const headers = new Headers({
    "Content-Type": upstream.headers.get("content-type") ?? contentType,
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
  });
  const disposition = safeContentDisposition(upstream.headers.get("content-disposition"));
  if (disposition !== null) headers.set("Content-Disposition", disposition);
  return new NextResponse(responseBody, { status: upstream.status, headers });
}

async function proxy(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  const { path: pathParts } = await context.params;
  const path = pathParts.join("/");
  const rule = findRule(request.method, path);
  if (rule === null) return genericJson(404, "management route not found");
  const query = validatedQuery(request, rule);
  if (query === null) return genericJson(404, "management route not found");

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
    const candidateBody = await request.text();
    if (Buffer.byteLength(candidateBody, "utf8") > MAX_BODY_BYTES) {
      return genericJson(413, "request too large");
    }
    if (candidateBody.length === 0 && rule.allowEmptyBody) {
      body = undefined;
    } else {
      const contentType = request.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase();
      if (contentType !== "application/json") return genericJson(415, "application/json required");
      body = candidateBody;
    }
  }

  let base: string;
  try {
    base = upstreamApiBase();
  } catch {
    return genericJson(503, "management upstream unavailable");
  }

  const headers = new Headers({ Accept: rule.responseKind === "report" ? "*/*" : "application/json" });
  if (authorization !== null && rule.authenticated) headers.set("Authorization", authorization);
  if (body !== undefined) headers.set("Content-Type", "application/json");

  let upstream: Response;
  try {
    upstream = await fetch(`${base}/${path}${query}`, {
      method: rule.method,
      headers,
      body,
      cache: "no-store",
      redirect: "error",
    });
  } catch {
    return genericJson(502, "management upstream request failed");
  }

  if (rule.responseKind === "report" && upstream.ok) return proxyReport(upstream);
  if (upstream.status === 204) {
    return new NextResponse(null, {
      status: 204,
      headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" },
    });
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

type RouteContext = Readonly<{ params: Promise<{ path: string[] }> }>;

export function GET(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  return proxy(request, context);
}

export function POST(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  return proxy(request, context);
}

export function PUT(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  return proxy(request, context);
}
