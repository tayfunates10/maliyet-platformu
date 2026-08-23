import { WorkspaceApiError } from "./calculation-workspace-api";

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const MANAGEMENT_PREFIX = "/api/management";

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

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function requireString(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  if (typeof value !== "string") throw new WorkspaceApiError(502, "invalid_response");
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

function parseResult(payload: unknown): DecisionAnalysisResult {
  if (!isRecord(payload) || !isRecord(payload.snapshot)) {
    throw new WorkspaceApiError(502, "invalid_response");
  }
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

function errorCode(status: number): string {
  if (status === 401) return "authentication_required";
  if (status === 403) return "access_denied";
  if (status === 413) return "request_too_large";
  if (status === 422) return "invalid_request";
  if (status === 429) return "rate_limited";
  return "request_failed";
}

export async function runDecisionAnalysis(
  token: string,
  organizationId: string,
  input: DecisionAnalysisInput,
): Promise<DecisionAnalysisResult> {
  if (!UUID_PATTERN.test(organizationId)) throw new WorkspaceApiError(0, "invalid_organization");
  if (token.length < 16 || token.length > 512) throw new WorkspaceApiError(0, "invalid_session");
  if (input.scenarios.length !== 3) throw new WorkspaceApiError(0, "invalid_request");

  const response = await fetch(
    `${MANAGEMENT_PREFIX}/organizations/${encodeURIComponent(organizationId)}/decision-analysis/investment-scenarios`,
    {
      method: "POST",
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${token}`,
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
    return parseResult(await response.json());
  } catch (error) {
    if (error instanceof WorkspaceApiError) throw error;
    throw new WorkspaceApiError(502, "invalid_response");
  }
}
