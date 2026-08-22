const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const MANAGEMENT_PREFIX = "/api/management";
const PAGE_SIZE = 100;
const MAX_PAGES = 100;

export type WorkspaceOrganization = Readonly<{
  id: string;
  slug: string;
  legal_name: string;
  role: string;
}>;

export type EngineSummary = Readonly<{
  key: string;
  title: string;
  engine_version: string;
  execution_requires_trusted_actor: boolean;
  regulatory_rules_applied: boolean;
}>;

export type CalculationSummary = Readonly<{
  id: string;
  organization_id: string;
  created_by_user_id: string;
  name: string;
  calculation_type: string;
  created_at: string;
  updated_at: string;
}>;

export class WorkspaceApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string) {
    super(code);
    this.name = "WorkspaceApiError";
    this.status = status;
    this.code = code;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function requireString(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  if (typeof value !== "string") throw new WorkspaceApiError(502, "invalid_response");
  return value;
}

function requireBoolean(record: Record<string, unknown>, key: string): boolean {
  const value = record[key];
  if (typeof value !== "boolean") throw new WorkspaceApiError(502, "invalid_response");
  return value;
}

function errorCode(status: number): string {
  if (status === 401) return "authentication_required";
  if (status === 403) return "access_denied";
  if (status === 404) return "not_found";
  if (status === 409) return "conflict";
  if (status === 413) return "request_too_large";
  if (status === 422) return "invalid_request";
  if (status === 429) return "rate_limited";
  return "request_failed";
}

async function requestJson(
  path: string,
  options: Readonly<{
    method?: "GET" | "POST";
    token?: string;
    body?: unknown;
  }> = {},
): Promise<unknown> {
  const headers = new Headers({ Accept: "application/json" });
  if (options.token !== undefined) {
    if (options.token.length < 16 || options.token.length > 512) {
      throw new WorkspaceApiError(0, "invalid_session");
    }
    headers.set("Authorization", `Bearer ${options.token}`);
  }
  let body: string | undefined;
  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(options.body);
  }
  const response = await fetch(`${MANAGEMENT_PREFIX}${path}`, {
    method: options.method ?? "GET",
    headers,
    body,
    credentials: "omit",
    cache: "no-store",
    redirect: "error",
    referrerPolicy: "no-referrer",
  });
  if (!response.ok) throw new WorkspaceApiError(response.status, errorCode(response.status));
  try {
    return await response.json();
  } catch {
    throw new WorkspaceApiError(502, "invalid_response");
  }
}

function parseOrganization(value: unknown): WorkspaceOrganization {
  if (!isRecord(value)) throw new WorkspaceApiError(502, "invalid_response");
  const id = requireString(value, "id");
  const slug = requireString(value, "slug");
  const legalName = requireString(value, "legal_name");
  const role = requireString(value, "role");
  if (!UUID_PATTERN.test(id) || slug.length === 0 || legalName.length === 0 || role.length === 0) {
    throw new WorkspaceApiError(502, "invalid_response");
  }
  return Object.freeze({ id, slug, legal_name: legalName, role });
}

function parseEngine(value: unknown): EngineSummary {
  if (!isRecord(value)) throw new WorkspaceApiError(502, "invalid_response");
  const key = requireString(value, "key");
  const title = requireString(value, "title");
  const engineVersion = requireString(value, "engine_version");
  if (key.length === 0 || key.length > 80 || title.length === 0 || engineVersion.length === 0) {
    throw new WorkspaceApiError(502, "invalid_response");
  }
  return Object.freeze({
    key,
    title,
    engine_version: engineVersion,
    execution_requires_trusted_actor: requireBoolean(value, "execution_requires_trusted_actor"),
    regulatory_rules_applied: requireBoolean(value, "regulatory_rules_applied"),
  });
}

function parseCalculation(value: unknown): CalculationSummary {
  if (!isRecord(value)) throw new WorkspaceApiError(502, "invalid_response");
  const id = requireString(value, "id");
  const organizationId = requireString(value, "organization_id");
  const creatorId = requireString(value, "created_by_user_id");
  const name = requireString(value, "name");
  const calculationType = requireString(value, "calculation_type");
  const createdAt = requireString(value, "created_at");
  const updatedAt = requireString(value, "updated_at");
  if (
    !UUID_PATTERN.test(id) ||
    !UUID_PATTERN.test(organizationId) ||
    !UUID_PATTERN.test(creatorId) ||
    name.length === 0 ||
    calculationType.length === 0 ||
    Number.isNaN(Date.parse(createdAt)) ||
    Number.isNaN(Date.parse(updatedAt))
  ) {
    throw new WorkspaceApiError(502, "invalid_response");
  }
  return Object.freeze({
    id,
    organization_id: organizationId,
    created_by_user_id: creatorId,
    name,
    calculation_type: calculationType,
    created_at: createdAt,
    updated_at: updatedAt,
  });
}

export async function loginWorkspace(email: string, password: string): Promise<string> {
  const payload = await requestJson("/auth/login", { method: "POST", body: { email, password } });
  if (!isRecord(payload)) throw new WorkspaceApiError(502, "invalid_response");
  const token = requireString(payload, "access_token");
  if (token.length < 16 || token.length > 512) throw new WorkspaceApiError(502, "invalid_response");
  return token;
}

export async function listWorkspaceOrganizations(token: string): Promise<readonly WorkspaceOrganization[]> {
  const payload = await requestJson("/organizations", { token });
  if (!Array.isArray(payload)) throw new WorkspaceApiError(502, "invalid_response");
  return Object.freeze(payload.map(parseOrganization));
}

export async function listWorkspaceEngines(token: string): Promise<readonly EngineSummary[]> {
  const payload = await requestJson("/engines", { token });
  if (!Array.isArray(payload)) throw new WorkspaceApiError(502, "invalid_response");
  return Object.freeze(payload.map(parseEngine));
}

export async function listCalculations(
  token: string,
  organizationId: string,
): Promise<readonly CalculationSummary[]> {
  if (!UUID_PATTERN.test(organizationId)) throw new WorkspaceApiError(0, "invalid_organization");
  const calculations: CalculationSummary[] = [];
  const seenIds = new Set<string>();
  for (let page = 0; page < MAX_PAGES; page += 1) {
    const offset = page * PAGE_SIZE;
    const payload = await requestJson(
      `/organizations/${encodeURIComponent(organizationId)}/calculations?limit=${PAGE_SIZE}&offset=${offset}`,
      { token },
    );
    if (!Array.isArray(payload)) throw new WorkspaceApiError(502, "invalid_response");
    const parsed = payload.map(parseCalculation);
    for (const calculation of parsed) {
      if (calculation.organization_id !== organizationId || seenIds.has(calculation.id)) {
        throw new WorkspaceApiError(502, "invalid_response");
      }
      seenIds.add(calculation.id);
      calculations.push(calculation);
    }
    if (parsed.length < PAGE_SIZE) return Object.freeze(calculations);
  }
  throw new WorkspaceApiError(502, "calculation_page_limit_exceeded");
}

export async function createCalculation(
  token: string,
  organizationId: string,
  input: Readonly<{ name: string; calculation_type: string }>,
): Promise<CalculationSummary> {
  if (!UUID_PATTERN.test(organizationId)) throw new WorkspaceApiError(0, "invalid_organization");
  const name = input.name.trim();
  const calculationType = input.calculation_type.trim();
  if (name.length < 1 || name.length > 240 || calculationType.length < 1 || calculationType.length > 80) {
    throw new WorkspaceApiError(0, "invalid_request");
  }
  const payload = await requestJson(`/organizations/${encodeURIComponent(organizationId)}/calculations`, {
    method: "POST",
    token,
    body: { name, calculation_type: calculationType },
  });
  const calculation = parseCalculation(payload);
  if (calculation.organization_id !== organizationId || calculation.calculation_type !== calculationType) {
    throw new WorkspaceApiError(502, "invalid_response");
  }
  return calculation;
}
