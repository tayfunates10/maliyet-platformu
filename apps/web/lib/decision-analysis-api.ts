import { WorkspaceApiError } from "./calculation-workspace-api";

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const MANAGEMENT_PREFIX = "/api/management";
const HISTORY_PAGE_SIZE = 50;

export type ScenarioKey = "pessimistic" | "normal" | "optimistic";

export type DecisionAnalysisInput = Readonly<{
  initial_investment: string;
  net_return: string;
  equity: string;
  net_income: string;
  invested_capital: string;
  net_operating_profit_after_tax: string;
  scenarios: readonly Readonly<{ key: ScenarioKey; revenue: string; costs: string }>[];
}>;

export type DecisionAnalysisResult = Readonly<{
  engine_version: string;
  roi_ratio: string;
  roe_ratio: string;
  roic_ratio: string;
  scenarios: readonly Readonly<{
    key: ScenarioKey;
    revenue: string;
    costs: string;
    profit: string;
    profit_margin_ratio: string | null;
  }>[];
}>;

export type DecisionAnalysisArtifact = Readonly<{
  artifact_id: string;
  input_sha256: string;
  output_sha256: string;
  created_at: string;
  result: DecisionAnalysisResult;
}>;

export type DecisionAnalysisHistoryItem = Readonly<{
  artifact_id: string;
  engine_version: string;
  input_sha256: string;
  output_sha256: string;
  created_at: string;
}>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function requireString(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  if (typeof value !== "string") throw new WorkspaceApiError(502, "invalid_response");
  return value;
}

function requireUuid(record: Record<string, unknown>, key: string): string {
  const value = requireString(record, key);
  if (!UUID_PATTERN.test(value)) throw new WorkspaceApiError(502, "invalid_response");
  return value;
}

function requireDigest(record: Record<string, unknown>, key: string): string {
  const value = requireString(record, key);
  if (!SHA256_PATTERN.test(value)) throw new WorkspaceApiError(502, "invalid_response");
  return value;
}

function parseScenario(value: unknown): DecisionAnalysisResult["scenarios"][number] {
  if (!isRecord(value)) throw new WorkspaceApiError(502, "invalid_response");
  const key = requireString(value, "key");
  if (key !== "pessimistic" && key !== "normal" && key !== "optimistic") {
    throw new WorkspaceApiError(502, "invalid_response");
  }
  const margin = value.profit_margin_ratio;
  if (margin !== null && typeof margin !== "string") {
    throw new WorkspaceApiError(502, "invalid_response");
  }
  return Object.freeze({
    key,
    revenue: requireString(value, "revenue"),
    costs: requireString(value, "costs"),
    profit: requireString(value, "profit"),
    profit_margin_ratio: margin,
  });
}

function parseResult(payload: Record<string, unknown>): DecisionAnalysisResult {
  if (!isRecord(payload.snapshot)) throw new WorkspaceApiError(502, "invalid_response");
  const snapshot = payload.snapshot;
  const engineVersion = requireString(snapshot, "engine_version");
  if (!isRecord(snapshot.investment) || !Array.isArray(snapshot.scenarios)) {
    throw new WorkspaceApiError(502, "invalid_response");
  }
  const scenarios = snapshot.scenarios.map(parseScenario);
  if (
    scenarios.length !== 3 ||
    scenarios[0]?.key !== "pessimistic" ||
    scenarios[1]?.key !== "normal" ||
    scenarios[2]?.key !== "optimistic"
  ) {
    throw new WorkspaceApiError(502, "invalid_response");
  }
  return Object.freeze({
    engine_version: engineVersion,
    roi_ratio: requireString(snapshot.investment, "roi_ratio"),
    roe_ratio: requireString(snapshot.investment, "roe_ratio"),
    roic_ratio: requireString(snapshot.investment, "roic_ratio"),
    scenarios: Object.freeze(scenarios),
  });
}

function parseArtifact(payload: unknown): DecisionAnalysisArtifact {
  if (!isRecord(payload)) throw new WorkspaceApiError(502, "invalid_response");
  return Object.freeze({
    artifact_id: requireUuid(payload, "artifact_id"),
    input_sha256: requireDigest(payload, "input_sha256"),
    output_sha256: requireDigest(payload, "output_sha256"),
    created_at: requireString(payload, "created_at"),
    result: parseResult(payload),
  });
}

function parseHistoryItem(payload: unknown): DecisionAnalysisHistoryItem {
  if (!isRecord(payload)) throw new WorkspaceApiError(502, "invalid_response");
  return Object.freeze({
    artifact_id: requireUuid(payload, "artifact_id"),
    engine_version: requireString(payload, "engine_version"),
    input_sha256: requireDigest(payload, "input_sha256"),
    output_sha256: requireDigest(payload, "output_sha256"),
    created_at: requireString(payload, "created_at"),
  });
}

function errorCode(status: number): string {
  if (status === 401) return "authentication_required";
  if (status === 403) return "access_denied";
  if (status === 404) return "analysis_not_found";
  if (status === 409) return "integrity_failed";
  if (status === 413) return "request_too_large";
  if (status === 422) return "invalid_request";
  if (status === 429) return "rate_limited";
  return "request_failed";
}

function validateIdentity(token: string, organizationId: string): void {
  if (!UUID_PATTERN.test(organizationId)) throw new WorkspaceApiError(0, "invalid_organization");
  if (token.length < 16 || token.length > 512) throw new WorkspaceApiError(0, "invalid_session");
}

function authenticatedHeaders(token: string): Readonly<Record<string, string>> {
  return Object.freeze({
    Accept: "application/json",
    Authorization: `Bearer ${token}`,
  });
}

export async function runDecisionAnalysis(
  token: string,
  organizationId: string,
  input: DecisionAnalysisInput,
): Promise<DecisionAnalysisArtifact> {
  validateIdentity(token, organizationId);
  if (input.scenarios.length !== 3) throw new WorkspaceApiError(0, "invalid_request");

  const response = await fetch(
    `${MANAGEMENT_PREFIX}/organizations/${encodeURIComponent(organizationId)}/decision-analysis/investment-scenarios`,
    {
      method: "POST",
      headers: {
        ...authenticatedHeaders(token),
        "Content-Type": "application/json",
      },
      body: JSON.stringify(input),
      credentials: "omit",
      cache: "no-store",
      redirect: "error",
      referrerPolicy: "no-referrer",
    },
  );
  if (!response.ok) throw new WorkspaceApiError(response.status, errorCode(response.status));
  try {
    return parseArtifact(await response.json());
  } catch (error) {
    if (error instanceof WorkspaceApiError) throw error;
    throw new WorkspaceApiError(502, "invalid_response");
  }
}

export async function listDecisionAnalysisHistory(
  token: string,
  organizationId: string,
): Promise<readonly DecisionAnalysisHistoryItem[]> {
  validateIdentity(token, organizationId);
  const response = await fetch(
    `${MANAGEMENT_PREFIX}/organizations/${encodeURIComponent(organizationId)}/decision-analysis/investment-scenarios?limit=${HISTORY_PAGE_SIZE}&offset=0`,
    {
      method: "GET",
      headers: authenticatedHeaders(token),
      credentials: "omit",
      cache: "no-store",
      redirect: "error",
      referrerPolicy: "no-referrer",
    },
  );
  if (!response.ok) throw new WorkspaceApiError(response.status, errorCode(response.status));
  try {
    const payload: unknown = await response.json();
    if (!Array.isArray(payload)) throw new WorkspaceApiError(502, "invalid_response");
    if (payload.length > HISTORY_PAGE_SIZE) throw new WorkspaceApiError(502, "invalid_response");
    return Object.freeze(payload.map(parseHistoryItem));
  } catch (error) {
    if (error instanceof WorkspaceApiError) throw error;
    throw new WorkspaceApiError(502, "invalid_response");
  }
}

export async function getDecisionAnalysisArtifact(
  token: string,
  organizationId: string,
  artifactId: string,
): Promise<DecisionAnalysisArtifact> {
  validateIdentity(token, organizationId);
  if (!UUID_PATTERN.test(artifactId)) throw new WorkspaceApiError(0, "invalid_artifact");
  const response = await fetch(
    `${MANAGEMENT_PREFIX}/organizations/${encodeURIComponent(organizationId)}/decision-analysis/investment-scenarios/${encodeURIComponent(artifactId)}`,
    {
      method: "GET",
      headers: authenticatedHeaders(token),
      credentials: "omit",
      cache: "no-store",
      redirect: "error",
      referrerPolicy: "no-referrer",
    },
  );
  if (!response.ok) throw new WorkspaceApiError(response.status, errorCode(response.status));
  try {
    return parseArtifact(await response.json());
  } catch (error) {
    if (error instanceof WorkspaceApiError) throw error;
    throw new WorkspaceApiError(502, "invalid_response");
  }
}
