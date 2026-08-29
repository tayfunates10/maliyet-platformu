import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { translatedFieldKeys, turkishFieldLabel } from "../lib/schema-field-labels.mjs";
import { transitionNullableValue } from "../lib/schema-nullability.mjs";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const apiClient = readFileSync(resolve(webRoot, "lib/calculation-workspace-api.ts"), "utf8");
const executionApi = readFileSync(resolve(webRoot, "lib/calculation-execution-api.ts"), "utf8");
const schemaTemplate = readFileSync(resolve(webRoot, "lib/json-schema-template.ts"), "utf8");
const workspace = readFileSync(resolve(webRoot, "components/calculation-workspace.tsx"), "utf8");
const executionPanel = readFileSync(resolve(webRoot, "components/calculation-execution-panel.tsx"), "utf8");
const schemaEditor = readFileSync(resolve(webRoot, "components/schema-field-editor.tsx"), "utf8");
const resultSummary = readFileSync(resolve(webRoot, "components/calculation-result-summary.tsx"), "utf8");
const proxy = readFileSync(resolve(webRoot, "app/api/management/[...path]/route.ts"), "utf8");
const page = readFileSync(resolve(webRoot, "app/calculations/page.tsx"), "utf8");

for (const source of [apiClient, executionApi, workspace, executionPanel, schemaEditor, resultSummary, proxy]) {
  assert.doesNotMatch(source, /localStorage|sessionStorage|indexedDB|document\.cookie/);
  assert.doesNotMatch(source, /console\.(?:log|debug|info|warn|error)/);
}

assert.match(apiClient, /const MANAGEMENT_PREFIX = "\/api\/management"/);
assert.match(apiClient, /const ORGANIZATION_PAGE_SIZE = 50/);
assert.match(apiClient, /const CALCULATION_PAGE_SIZE = 50/);
assert.match(apiClient, /credentials:\s*"omit"/);
assert.match(apiClient, /cache:\s*"no-store"/);
assert.match(apiClient, /redirect:\s*"error"/);
assert.match(apiClient, /referrerPolicy:\s*"no-referrer"/);
assert.match(apiClient, /Authorization: `Bearer \$\{token\}`/);
assert.match(apiClient, /logoutWorkspace/);
assert.match(apiClient, /MANAGEMENT_PREFIX\}\/auth\/logout/);
assert.match(apiClient, /response\.status !== 204/);
assert.match(apiClient, /listWorkspaceOrganizations/);
assert.match(apiClient, /organization_page_limit_exceeded/);
assert.match(apiClient, /listWorkspaceEngines/);
assert.match(apiClient, /listCalculations/);
assert.match(apiClient, /createCalculation/);
assert.match(apiClient, /calculation\.organization_id !== organizationId/);
assert.match(apiClient, /seenIds/);
assert.doesNotMatch(apiClient, /fetch\(\s*["'`]https?:\/\//);

assert.match(executionApi, /const MANAGEMENT_PREFIX = "\/api\/management"/);
assert.match(executionApi, /ENGINE_KEY_PATTERN/);
assert.match(executionApi, /SHA256_PATTERN/);
assert.match(executionApi, /credentials:\s*"omit"/);
assert.match(executionApi, /cache:\s*"no-store"/);
assert.match(executionApi, /redirect:\s*"error"/);
assert.match(executionApi, /referrerPolicy:\s*"no-referrer"/);
assert.match(executionApi, /new TextEncoder\(\)\.encode\(body\)\.byteLength > 16_384/);
assert.match(executionApi, /getEngineDetail/);
assert.match(executionApi, /executeCalculation/);
assert.match(executionApi, /getLatestCalculationVersion/);
assert.match(executionApi, /returnedCalculationId !== calculationId/);
assert.match(executionApi, /returnedOrganizationId !== organizationId/);
assert.match(executionApi, /returnedEngineKey !== engineKey/);
assert.doesNotMatch(executionApi, /parseFloat|parseInt/);
assert.doesNotMatch(executionApi, /fetch\(\s*["'`]https?:\/\//);

assert.match(schemaTemplate, /#\/\$defs\//);
assert.match(schemaTemplate, /schema_depth_exceeded/);
assert.match(schemaTemplate, /buildSchemaTemplate/);
assert.match(schemaTemplate, /listRequiredFields/);
assert.match(schemaTemplate, /templateForRequiredArray/);
assert.match(schemaTemplate, /return \[templateFor\(items, root, depth \+ 1\)\]/);
assert.match(schemaTemplate, /required\.has\(key\)/);
assert.doesNotMatch(schemaTemplate, /eval|Function\(/);

assert.match(proxy, /\^auth\\\/logout\$/);
assert.match(proxy, /\^organizations\$/);
assert.match(proxy, /\^engines\$/);
assert.match(proxy, /ENGINE_KEY/);
assert.match(proxy, /REPORT_FORMAT/);
assert.match(proxy, /MAX_REPORT_BYTES/);
assert.match(proxy, /responseKind:\s*"report"/);
assert.match(proxy, /safeContentDisposition/);
assert.match(proxy, /REPORT_CONTENT_TYPES/);
assert.match(proxy, /readBoundedReportBody/);
assert.match(proxy, /upstream\.body\.getReader\(\)/);
assert.match(proxy, /reader\.cancel\(\)/);
assert.match(proxy, /content-length/);
assert.doesNotMatch(proxy, /upstream\.arrayBuffer\(\)/);
assert.match(proxy, /organizations\/\$\{UUID\}\/calculations\/\$\{UUID\}\/versions/);
assert.match(proxy, /report\\\\\.\$\{REPORT_FORMAT\}/);
assert.match(proxy, /organizations\/\$\{UUID\}\/calculations\/\$\{UUID\}\/execute\/\$\{ENGINE_KEY\}/);
assert.match(proxy, /allowDeploymentPagination:\s*true/);
assert.match(proxy, /allowEmptyBody:\s*true/);
assert.match(proxy, /upstream\.status === 204/);
assert.match(proxy, /authorization\.startsWith\("Bearer "\)/);
assert.doesNotMatch(proxy, /Access-Control-Allow-Origin/);
assert.doesNotMatch(proxy, /\^.*\.\*.*\$/);

assert.match(workspace, /type="password"/);
assert.match(workspace, /setPassword\(""\)/);
assert.match(workspace, /setToken\(null\)/);
assert.match(workspace, /Promise\.all/);
assert.match(workspace, /WRITE_ROLES/);
assert.match(workspace, /listCalculations/);
assert.match(workspace, /createCalculation/);
assert.match(workspace, /await logoutWorkspace\(token\)/);
assert.match(workspace, /CalculationExecutionPanel/);
assert.match(workspace, /selectedCalculationId/);
assert.match(workspace, /Oturumu kapat/);
assert.match(workspace, /token=\{token\}/);
assert.doesNotMatch(workspace, /useEffect/);
assert.doesNotMatch(workspace, /(?:value|defaultValue|data-[\w-]+|aria-[\w-]+)=\{token\}|>\s*\{token\}\s*</);

assert.match(executionPanel, /getEngineDetail/);
assert.match(executionPanel, /buildSchemaTemplate/);
assert.match(executionPanel, /SchemaFieldEditor/);
assert.match(executionPanel, /CalculationResultSummary/);
assert.match(executionPanel, /executeCalculation/);
assert.match(executionPanel, /getLatestCalculationVersion/);
assert.match(executionPanel, /REPORT_FORMATS/);
assert.match(executionPanel, /downloadReport/);
assert.match(executionPanel, /Authorization: `Bearer \$\{token\}`/);
assert.match(executionPanel, /credentials:\s*"same-origin"/);
assert.match(executionPanel, /redirect:\s*"error"/);
assert.match(executionPanel, /referrerPolicy:\s*"no-referrer"/);
assert.match(executionPanel, /response\.headers\.get\("content-type"\)/);
assert.match(executionPanel, /URL\.createObjectURL/);
assert.match(executionPanel, /URL\.revokeObjectURL/);
assert.match(executionPanel, /<fieldset className=\{styles\.listActions\}>/);
assert.match(executionPanel, /<legend>Sürüm \{reportVersion\} rapor indirmeleri<\/legend>/);
assert.doesNotMatch(executionPanel, /role="group"/);
assert.match(executionPanel, /immutable sürüm/);
assert.match(executionPanel, /Decimal alanları sayı değil metin/);
assert.doesNotMatch(executionPanel, /JSON\.parse\(/);
assert.doesNotMatch(executionPanel, /parseFloat|parseInt/);
assert.doesNotMatch(executionPanel, /dangerouslySetInnerHTML|innerHTML/);
assert.doesNotMatch(executionPanel, /fetch\(\s*["'`]https?:\/\//);

assert.match(schemaEditor, /valueAsNumber/);
assert.match(schemaEditor, /resolved\.type === "string"/);
assert.match(schemaEditor, /resolved\.type === "integer"/);
assert.match(schemaEditor, /resolved\.type === "boolean"/);
assert.match(schemaEditor, /resolved\.type === "array"/);
assert.match(schemaEditor, /resolved\.type === "object"/);
assert.match(schemaEditor, /enumValues/);
assert.match(schemaEditor, /#\/\$defs\//);
assert.match(schemaEditor, /allowsNull/);
assert.match(schemaEditor, /transitionNullableValue/);
assert.match(schemaEditor, /Bu alanı kullan/);
assert.match(schemaEditor, /Object\.hasOwn\(recordValue, key\)/);
assert.doesNotMatch(schemaEditor, /dangerouslySetInnerHTML|innerHTML|eval|Function\(/);
assert.doesNotMatch(schemaEditor, /parseFloat|parseInt/);

const retainedNullable = { capacity_quantity: "12.5" };
assert.equal(
  transitionNullableValue(false, retainedNullable, () => ({ capacity_quantity: "0" })),
  null,
  "disabling a nullable field must restore explicit null",
);
assert.equal(
  transitionNullableValue(true, "12.5", () => "0"),
  "12.5",
  "enabling an already-populated nullable field must retain its current value",
);
let factoryCalls = 0;
const enabledFromNull = transitionNullableValue(true, null, () => {
  factoryCalls += 1;
  return { capacity_quantity: "0" };
});
assert.deepEqual(enabledFromNull, { capacity_quantity: "0" });
assert.equal(factoryCalls, 1, "enabling a null field must create one non-null value exactly once");

assert.match(resultSummary, /Object\.entries\(snapshot\)/);
assert.match(resultSummary, /slice\(0, 16\)/);
assert.doesNotMatch(resultSummary, /dangerouslySetInnerHTML|innerHTML/);

assert.match(page, /CalculationWorkspace/);
assert.match(page, /Sektör motoru yalnız API allowlist’inden seçilir/);

// Engine schema field labels must reach the Turkish UI, never the Pydantic English title.
assert.match(schemaEditor, /turkishFieldLabel/);
assert.match(schemaEditor, /const turkish = turkishFieldLabel\(key\);/);
assert.match(schemaEditor, /if \(turkish !== null\) return turkish;/);

const labelledKeys = translatedFieldKeys();
assert.ok(labelledKeys.length >= 90, "engine field label coverage must not silently shrink");
for (const key of labelledKeys) {
  const label = turkishFieldLabel(key);
  assert.equal(typeof label, "string");
  assert.notEqual(label.trim(), "", `field label for ${key} must not be blank`);
  assert.doesNotMatch(label, /^[a-z0-9_]+$/, `field label for ${key} must not echo the raw schema key`);
}

// Representative keys across manufacturing, commerce, logistics, tax and depreciation engines.
assert.equal(turkishFieldLabel("theoretical_output_per_recipe"), "Reçete başına teorik çıktı");
assert.equal(turkishFieldLabel("package_content_quantity"), "Paket içerik miktarı");
assert.equal(turkishFieldLabel("quality_rejected_quantity"), "Kalite reddi miktarı");
assert.equal(turkishFieldLabel("commission_rate"), "Komisyon oranı");
assert.equal(turkishFieldLabel("loaded_km"), "Yüklü km");
assert.equal(turkishFieldLabel("useful_life_months"), "Faydalı ömür (ay)");
assert.equal(turkishFieldLabel("accounting_profit_before_tax"), "Vergi öncesi muhasebe kârı");
assert.equal(turkishFieldLabel("declared_monthly_earnings"), "Beyan edilen aylık kazanç");

// An engine field the dictionary does not know must fall back, never render blank.
assert.equal(turkishFieldLabel("field_added_by_a_future_engine"), null);

console.log("Calculation workspace security contract: PASS");
