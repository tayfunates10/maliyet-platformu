/**
 * Typed client for the read-only tenant dashboard projection.
 *
 * Every monetary field stays a string end to end. The API sends the exact
 * Decimal text an engine stored, and this module never parses one into a
 * JavaScript number: doing so would silently round an authoritative financial
 * result through binary floating point. Formatting for display happens at the
 * render boundary and is applied to the string, not to a recomputed value.
 */

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const MANAGEMENT_PREFIX = "/api/management";
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const DECIMAL_PATTERN = /^-?\d+(?:\.\d+)?$/;
const MAX_COLLECTION_LENGTH = 200;

export type BaselineStatus = "ready" | "degraded" | "unavailable";
export type RegulatoryRuleState = "effective" | "not_effective" | "ambiguous";

export type DashboardOrganization = Readonly<{
  id: string;
  slug: string;
  legal_name: string;
  primary_sector: string | null;
  city: string | null;
  role: string;
}>;

export type CostCategoryGroup = Readonly<{
  key: string;
  entries: ReadonlyArray<readonly [string, string]>;
}>;

export type DashboardCalculation = Readonly<{
  calculation_id: string;
  name: string;
  calculation_type: string;
  engine_key: string | null;
  engine_title: string | null;
  engine_version: string | null;
  version_number: number | null;
  computed_at: string | null;
  output_sha256: string | null;
  total_cost: string | null;
  unit_cost: string | null;
  margin_ratio: string | null;
  cost_categories: readonly CostCategoryGroup[];
}>;

export type DashboardTimelineEntry = Readonly<{
  calculation_id: string;
  calculation_name: string;
  engine_key: string | null;
  version_number: number;
  computed_at: string;
  total_cost: string | null;
  unit_cost: string | null;
}>;

export type RegulatorySource = Readonly<{
  authority: string;
  title: string;
  official_reference: string | null;
  published_on: string | null;
  retrieved_at: string;
  content_sha256: string;
}>;

export type RegulatoryRule = Readonly<{
  code: string;
  category: string;
  description: string;
  state: RegulatoryRuleState;
  effective_from: string | null;
  effective_to: string | null;
  revision: number | null;
}>;

export type RegulatoryBaseline = Readonly<{
  status: BaselineStatus;
  dataset: string | null;
  dataset_version: number | null;
  reviewed_on: string | null;
  evaluated_at: string;
  source_count: number;
  rule_count: number;
  effective_rule_count: number;
  issues: readonly string[];
  sources: readonly RegulatorySource[];
  rules: readonly RegulatoryRule[];
}>;

export type DecisionAnalysisSummary = Readonly<{
  artifact_count: number;
  latest_artifact_id: string | null;
  latest_engine_version: string | null;
  latest_created_at: string | null;
  latest_output_sha256: string | null;
}>;

export type WidgetSummary = Readonly<{
  deployment_count: number;
  active_deployment_count: number;
  branding_profile_count: number;
  published_presentation_count: number;
}>;

export type DashboardOverview = Readonly<{
  organization: DashboardOrganization;
  generated_at: string;
  calculation_count: number;
  calculations: readonly DashboardCalculation[];
  timeline: readonly DashboardTimelineEntry[];
  regulatory_baseline: RegulatoryBaseline;
  decision_analysis: DecisionAnalysisSummary;
  widget: WidgetSummary;
}>;

export class DashboardApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string) {
    super(code);
    this.name = "DashboardApiError";
    this.status = status;
    this.code = code;
  }
}

function invalid(): never {
  throw new DashboardApiError(502, "invalid_response");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function requireString(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  if (typeof value !== "string" || value.length === 0) invalid();
  return value;
}

function optionalString(record: Record<string, unknown>, key: string): string | null {
  const value = record[key];
  if (value === null || value === undefined) return null;
  if (typeof value !== "string" || value.length === 0) invalid();
  return value;
}

/** Accept a Decimal only as text; never coerce it to a JavaScript number. */
function optionalDecimalText(record: Record<string, unknown>, key: string): string | null {
  const value = optionalString(record, key);
  if (value === null) return null;
  if (value.length > 80 || !DECIMAL_PATTERN.test(value)) invalid();
  return value;
}

function requireCount(record: Record<string, unknown>, key: string): number {
  const value = record[key];
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) invalid();
  return value;
}

function optionalPositiveInteger(record: Record<string, unknown>, key: string): number | null {
  const value = record[key];
  if (value === null || value === undefined) return null;
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) invalid();
  return value;
}

function requireArray(record: Record<string, unknown>, key: string): readonly unknown[] {
  const value = record[key];
  if (!Array.isArray(value) || value.length > MAX_COLLECTION_LENGTH) invalid();
  return value;
}

function requireUuid(record: Record<string, unknown>, key: string): string {
  const value = requireString(record, key);
  if (!UUID_PATTERN.test(value)) invalid();
  return value;
}

function optionalUuid(record: Record<string, unknown>, key: string): string | null {
  const value = optionalString(record, key);
  if (value !== null && !UUID_PATTERN.test(value)) invalid();
  return value;
}

function optionalSha256(record: Record<string, unknown>, key: string): string | null {
  const value = optionalString(record, key);
  if (value !== null && !SHA256_PATTERN.test(value)) invalid();
  return value;
}

function parseOrganization(value: unknown): DashboardOrganization {
  if (!isRecord(value)) invalid();
  return Object.freeze({
    id: requireUuid(value, "id"),
    slug: requireString(value, "slug"),
    legal_name: requireString(value, "legal_name"),
    primary_sector: optionalString(value, "primary_sector"),
    city: optionalString(value, "city"),
    role: requireString(value, "role"),
  });
}

function parseCostCategoryGroup(value: unknown): CostCategoryGroup {
  if (!isRecord(value)) invalid();
  const entries = value.entries;
  if (!isRecord(entries)) invalid();
  const parsed: (readonly [string, string])[] = [];
  for (const [name, amount] of Object.entries(entries)) {
    if (typeof amount !== "string" || !DECIMAL_PATTERN.test(amount)) invalid();
    parsed.push(Object.freeze([name, amount] as const));
  }
  if (parsed.length > MAX_COLLECTION_LENGTH) invalid();
  return Object.freeze({ key: requireString(value, "key"), entries: Object.freeze(parsed) });
}

function parseCalculation(value: unknown): DashboardCalculation {
  if (!isRecord(value)) invalid();
  return Object.freeze({
    calculation_id: requireUuid(value, "calculation_id"),
    name: requireString(value, "name"),
    calculation_type: requireString(value, "calculation_type"),
    engine_key: optionalString(value, "engine_key"),
    engine_title: optionalString(value, "engine_title"),
    engine_version: optionalString(value, "engine_version"),
    version_number: optionalPositiveInteger(value, "version_number"),
    computed_at: optionalString(value, "computed_at"),
    output_sha256: optionalSha256(value, "output_sha256"),
    total_cost: optionalDecimalText(value, "total_cost"),
    unit_cost: optionalDecimalText(value, "unit_cost"),
    margin_ratio: optionalDecimalText(value, "margin_ratio"),
    cost_categories: Object.freeze(
      requireArray(value, "cost_categories").map(parseCostCategoryGroup),
    ),
  });
}

function parseTimelineEntry(value: unknown): DashboardTimelineEntry {
  if (!isRecord(value)) invalid();
  const versionNumber = optionalPositiveInteger(value, "version_number");
  if (versionNumber === null) invalid();
  return Object.freeze({
    calculation_id: requireUuid(value, "calculation_id"),
    calculation_name: requireString(value, "calculation_name"),
    engine_key: optionalString(value, "engine_key"),
    version_number: versionNumber,
    computed_at: requireString(value, "computed_at"),
    total_cost: optionalDecimalText(value, "total_cost"),
    unit_cost: optionalDecimalText(value, "unit_cost"),
  });
}

function parseRegulatorySource(value: unknown): RegulatorySource {
  if (!isRecord(value)) invalid();
  const digest = optionalSha256(value, "content_sha256");
  if (digest === null) invalid();
  return Object.freeze({
    authority: requireString(value, "authority"),
    title: requireString(value, "title"),
    official_reference: optionalString(value, "official_reference"),
    published_on: optionalString(value, "published_on"),
    retrieved_at: requireString(value, "retrieved_at"),
    content_sha256: digest,
  });
}

function parseRuleState(value: unknown): RegulatoryRuleState {
  if (value === "effective" || value === "not_effective" || value === "ambiguous") return value;
  return invalid();
}

function parseRegulatoryRule(value: unknown): RegulatoryRule {
  if (!isRecord(value)) invalid();
  return Object.freeze({
    code: requireString(value, "code"),
    category: requireString(value, "category"),
    description: requireString(value, "description"),
    state: parseRuleState(value.state),
    effective_from: optionalString(value, "effective_from"),
    effective_to: optionalString(value, "effective_to"),
    revision: optionalPositiveInteger(value, "revision"),
  });
}

function parseBaselineStatus(value: unknown): BaselineStatus {
  if (value === "ready" || value === "degraded" || value === "unavailable") return value;
  return invalid();
}

function parseRegulatoryBaseline(value: unknown): RegulatoryBaseline {
  if (!isRecord(value)) invalid();
  const issues = requireArray(value, "issues").map((issue) => {
    if (typeof issue !== "string" || issue.length === 0 || issue.length > 400) invalid();
    return issue;
  });
  const baseline = Object.freeze({
    status: parseBaselineStatus(value.status),
    dataset: optionalString(value, "dataset"),
    dataset_version: optionalPositiveInteger(value, "dataset_version"),
    reviewed_on: optionalString(value, "reviewed_on"),
    evaluated_at: requireString(value, "evaluated_at"),
    source_count: requireCount(value, "source_count"),
    rule_count: requireCount(value, "rule_count"),
    effective_rule_count: requireCount(value, "effective_rule_count"),
    issues: Object.freeze(issues),
    sources: Object.freeze(requireArray(value, "sources").map(parseRegulatorySource)),
    rules: Object.freeze(requireArray(value, "rules").map(parseRegulatoryRule)),
  });
  // Fail closed: a clean status may never coexist with reported problems, and the
  // effective count may never exceed the curated rule count.
  if (baseline.status === "ready" && baseline.issues.length > 0) invalid();
  if (baseline.effective_rule_count > baseline.rule_count) invalid();
  return baseline;
}

function parseDecisionAnalysis(value: unknown): DecisionAnalysisSummary {
  if (!isRecord(value)) invalid();
  return Object.freeze({
    artifact_count: requireCount(value, "artifact_count"),
    latest_artifact_id: optionalUuid(value, "latest_artifact_id"),
    latest_engine_version: optionalString(value, "latest_engine_version"),
    latest_created_at: optionalString(value, "latest_created_at"),
    latest_output_sha256: optionalSha256(value, "latest_output_sha256"),
  });
}

function parseWidget(value: unknown): WidgetSummary {
  if (!isRecord(value)) invalid();
  const summary = Object.freeze({
    deployment_count: requireCount(value, "deployment_count"),
    active_deployment_count: requireCount(value, "active_deployment_count"),
    branding_profile_count: requireCount(value, "branding_profile_count"),
    published_presentation_count: requireCount(value, "published_presentation_count"),
  });
  if (summary.active_deployment_count > summary.deployment_count) invalid();
  return summary;
}

function parseDashboard(value: unknown, organizationId: string): DashboardOverview {
  if (!isRecord(value)) invalid();
  const organization = parseOrganization(value.organization);
  // The projection must belong to the tenant that was requested.
  if (organization.id.toLowerCase() !== organizationId.toLowerCase()) invalid();
  return Object.freeze({
    organization,
    generated_at: requireString(value, "generated_at"),
    calculation_count: requireCount(value, "calculation_count"),
    calculations: Object.freeze(requireArray(value, "calculations").map(parseCalculation)),
    timeline: Object.freeze(requireArray(value, "timeline").map(parseTimelineEntry)),
    regulatory_baseline: parseRegulatoryBaseline(value.regulatory_baseline),
    decision_analysis: parseDecisionAnalysis(value.decision_analysis),
    widget: parseWidget(value.widget),
  });
}

function errorCode(status: number): string {
  if (status === 401) return "authentication_required";
  if (status === 403) return "access_denied";
  if (status === 404) return "not_found";
  if (status === 429) return "rate_limited";
  return "request_failed";
}

function authorizedHeaders(token: string): Headers {
  if (token.length < 16 || token.length > 512) {
    throw new DashboardApiError(0, "invalid_session");
  }
  return new Headers({ Accept: "application/json", Authorization: `Bearer ${token}` });
}

export async function fetchDashboard(
  token: string,
  organizationId: string,
): Promise<DashboardOverview> {
  if (!UUID_PATTERN.test(organizationId)) throw new DashboardApiError(0, "invalid_request");
  const response = await fetch(
    `${MANAGEMENT_PREFIX}/organizations/${organizationId}/dashboard`,
    {
      method: "GET",
      headers: authorizedHeaders(token),
      credentials: "omit",
      cache: "no-store",
      redirect: "error",
      referrerPolicy: "no-referrer",
    },
  );
  if (!response.ok) throw new DashboardApiError(response.status, errorCode(response.status));
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new DashboardApiError(502, "invalid_response");
  }
  return parseDashboard(payload, organizationId);
}
