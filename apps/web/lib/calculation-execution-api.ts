const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const ENGINE_KEY_PATTERN = /^[a-z][a-z0-9_]{0,79}$/;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const MANAGEMENT_PREFIX = "/api/management";

export type EngineDetail = Readonly<{
  key: string;
  title: string;
  engine_version: string;
  execution_requires_trusted_actor: boolean;
  regulatory_rules_applied: boolean;
  input_schema: Readonly<Record<string, unknown>>;
}>;

export type CalculationExecution = Readonly<{
  calculation_id: string;
  calculation_version_id: string;
  version: number;
  engine_key: string;
  engine_version: string;
  input_sha256: string;
  ruleset_sha256: string;
  output_sha256: string;
  output_snapshot: Readonly<Record<string, unknown>>;
}>;

export type CalculationVersion = Readonly<{
  id: string;
  calculation_id: string;
  organization_id: string;
  version: number;
  engine_key: string | null;
  engine_version: string;
  output_snapshot: Readonly<Record<string, unknown>>;
  output_sha256: string | null;
  created_at: string;
}>;

export class CalculationExecutionApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string) {
    super(code);
    this.name = "CalculationExecutionApiError";
    this.status = status;
    this.code = code;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function requireString(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  if (typeof value !== "string") throw new CalculationExecutionApiError(502, "invalid_response");
  return value;
}

function requireBoolean(record: Record<string, unknown>, key: string): boolean {
  const value = record[key];
  if (typeof value !== "boolean") throw new CalculationExecutionApiError(502, "invalid_response");
  return value;
}

function requirePositiveInteger(record: Record<string, unknown>, key: string): number {
  const value = record[key];
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 1) {
    throw new CalculationExecutionApiError(502, "invalid_response");
  }
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

function authorizedHeaders(token: string): Headers {
  if (token.length < 16 || token.length > 512) throw new CalculationExecutionApiError(0, "invalid_session");
  return new Headers({ Accept: "application/json", Authorization: `Bearer ${token}` });
}

async function requestJson(
  path: string,
  options: Readonly<{ method?: "GET" | "POST"; token: string; body?: unknown }>,
): Promise<unknown> {
  const headers = authorizedHeaders(options.token);
  let body: string | undefined;
  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(options.body);
    if (new TextEncoder().encode(body).byteLength > 16_384) {
      throw new CalculationExecutionApiError(0, "request_too_large");
    }
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
  if (!response.ok) throw new CalculationExecutionApiError(response.status, errorCode(response.status));
  try {
    return await response.json();
  } catch {
    throw new CalculationExecutionApiError(502, "invalid_response");
  }
}

function validateIdentity(organizationId: string, calculationId: string, engineKey: string): void {
  if (!UUID_PATTERN.test(organizationId) || !UUID_PATTERN.test(calculationId) || !ENGINE_KEY_PATTERN.test(engineKey)) {
    throw new CalculationExecutionApiError(0, "invalid_request");
  }
}

function parseEngineDetail(value: unknown, expectedKey: string): EngineDetail {
  if (!isRecord(value)) throw new CalculationExecutionApiError(502, "invalid_response");
  const key = requireString(value, "key");
  const title = requireString(value, "title");
  const engineVersion = requireString(value, "engine_version");
  const inputSchema = value.input_schema;
  if (key !== expectedKey || !ENGINE_KEY_PATTERN.test(key) || title.length === 0 || engineVersion.length === 0 || !isRecord(inputSchema)) {
    throw new CalculationExecutionApiError(502, "invalid_response");
  }
  return Object.freeze({
    key,
    title,
    engine_version: engineVersion,
    execution_requires_trusted_actor: requireBoolean(value, "execution_requires_trusted_actor"),
    regulatory_rules_applied: requireBoolean(value, "regulatory_rules_applied"),
    input_schema: Object.freeze({ ...inputSchema }),
  });
}

function parseExecution(value: unknown, calculationId: string, engineKey: string): CalculationExecution {
  if (!isRecord(value)) throw new CalculationExecutionApiError(502, "invalid_response");
  const returnedCalculationId = requireString(value, "calculation_id");
  const versionId = requireString(value, "calculation_version_id");
  const returnedEngineKey = requireString(value, "engine_key");
  const engineVersion = requireString(value, "engine_version");
  const inputSha = requireString(value, "input_sha256");
  const rulesetSha = requireString(value, "ruleset_sha256");
  const outputSha = requireString(value, "output_sha256");
  const outputSnapshot = value.output_snapshot;
  if (
    returnedCalculationId !== calculationId ||
    !UUID_PATTERN.test(versionId) ||
    returnedEngineKey !== engineKey ||
    engineVersion.length === 0 ||
    !SHA256_PATTERN.test(inputSha) ||
    !SHA256_PATTERN.test(rulesetSha) ||
    !SHA256_PATTERN.test(outputSha) ||
    !isRecord(outputSnapshot)
  ) {
    throw new CalculationExecutionApiError(502, "invalid_response");
  }
  return Object.freeze({
    calculation_id: returnedCalculationId,
    calculation_version_id: versionId,
    version: requirePositiveInteger(value, "version"),
    engine_key: returnedEngineKey,
    engine_version: engineVersion,
    input_sha256: inputSha,
    ruleset_sha256: rulesetSha,
    output_sha256: outputSha,
    output_snapshot: Object.freeze({ ...outputSnapshot }),
  });
}

function parseVersion(value: unknown, organizationId: string, calculationId: string): CalculationVersion {
  if (!isRecord(value)) throw new CalculationExecutionApiError(502, "invalid_response");
  const id = requireString(value, "id");
  const returnedCalculationId = requireString(value, "calculation_id");
  const returnedOrganizationId = requireString(value, "organization_id");
  const engineKeyValue = value.engine_key;
  const engineKey = engineKeyValue === null ? null : requireString(value, "engine_key");
  const engineVersion = requireString(value, "engine_version");
  const outputSnapshot = value.output_snapshot;
  const outputShaValue = value.output_sha256;
  const outputSha = outputShaValue === null ? null : requireString(value, "output_sha256");
  const createdAt = requireString(value, "created_at");
  if (
    !UUID_PATTERN.test(id) ||
    returnedCalculationId !== calculationId ||
    returnedOrganizationId !== organizationId ||
    (engineKey !== null && !ENGINE_KEY_PATTERN.test(engineKey)) ||
    engineVersion.length === 0 ||
    !isRecord(outputSnapshot) ||
    (outputSha !== null && !SHA256_PATTERN.test(outputSha)) ||
    Number.isNaN(Date.parse(createdAt))
  ) {
    throw new CalculationExecutionApiError(502, "invalid_response");
  }
  return Object.freeze({
    id,
    calculation_id: returnedCalculationId,
    organization_id: returnedOrganizationId,
    version: requirePositiveInteger(value, "version"),
    engine_key: engineKey,
    engine_version: engineVersion,
    output_snapshot: Object.freeze({ ...outputSnapshot }),
    output_sha256: outputSha,
    created_at: createdAt,
  });
}

export async function getEngineDetail(token: string, engineKey: string): Promise<EngineDetail> {
  if (!ENGINE_KEY_PATTERN.test(engineKey)) throw new CalculationExecutionApiError(0, "invalid_request");
  const payload = await requestJson(`/engines/${encodeURIComponent(engineKey)}`, { token });
  return parseEngineDetail(payload, engineKey);
}

export async function executeCalculation(
  token: string,
  organizationId: string,
  calculationId: string,
  engineKey: string,
  input: Readonly<Record<string, unknown>>,
): Promise<CalculationExecution> {
  validateIdentity(organizationId, calculationId, engineKey);
  const payload = await requestJson(
    `/organizations/${encodeURIComponent(organizationId)}/calculations/${encodeURIComponent(calculationId)}/execute/${encodeURIComponent(engineKey)}`,
    { method: "POST", token, body: input },
  );
  return parseExecution(payload, calculationId, engineKey);
}

export async function getLatestCalculationVersion(
  token: string,
  organizationId: string,
  calculationId: string,
): Promise<CalculationVersion | null> {
  if (!UUID_PATTERN.test(organizationId) || !UUID_PATTERN.test(calculationId)) {
    throw new CalculationExecutionApiError(0, "invalid_request");
  }
  const payload = await requestJson(
    `/organizations/${encodeURIComponent(organizationId)}/calculations/${encodeURIComponent(calculationId)}/versions?limit=1&offset=0`,
    { token },
  );
  if (!Array.isArray(payload) || payload.length > 1) throw new CalculationExecutionApiError(502, "invalid_response");
  return payload.length === 0 ? null : parseVersion(payload[0], organizationId, calculationId);
}
