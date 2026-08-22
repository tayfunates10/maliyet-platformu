import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const apiClient = readFileSync(resolve(webRoot, "lib/calculation-workspace-api.ts"), "utf8");
const executionApi = readFileSync(resolve(webRoot, "lib/calculation-execution-api.ts"), "utf8");
const schemaTemplate = readFileSync(resolve(webRoot, "lib/json-schema-template.ts"), "utf8");
const workspace = readFileSync(resolve(webRoot, "components/calculation-workspace.tsx"), "utf8");
const executionPanel = readFileSync(resolve(webRoot, "components/calculation-execution-panel.tsx"), "utf8");
const proxy = readFileSync(resolve(webRoot, "app/api/management/[...path]/route.ts"), "utf8");
const page = readFileSync(resolve(webRoot, "app/calculations/page.tsx"), "utf8");

for (const source of [apiClient, executionApi, workspace, executionPanel, proxy]) {
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
assert.doesNotMatch(executionApi, /Number\(|parseFloat|parseInt/);
assert.doesNotMatch(executionApi, /fetch\(\s*["'`]https?:\/\//);

assert.match(schemaTemplate, /#\/\$defs\//);
assert.match(schemaTemplate, /schema_depth_exceeded/);
assert.match(schemaTemplate, /buildSchemaTemplate/);
assert.match(schemaTemplate, /listRequiredFields/);
assert.doesNotMatch(schemaTemplate, /eval|Function\(/);

assert.match(proxy, /\^auth\\\/logout\$/);
assert.match(proxy, /\^organizations\$/);
assert.match(proxy, /\^engines\$/);
assert.match(proxy, /ENGINE_KEY/);
assert.match(proxy, /\^engines\/\$\{ENGINE_KEY\}\$/);
assert.match(proxy, /organizations\/\$\{UUID\}\/calculations\/\$\{UUID\}\/versions/);
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
assert.match(executionPanel, /JSON\.parse\(inputText\)/);
assert.match(executionPanel, /executeCalculation/);
assert.match(executionPanel, /getLatestCalculationVersion/);
assert.match(executionPanel, /immutable sürüm/);
assert.match(executionPanel, /Decimal alanları JSON sayı değil metin/);
assert.doesNotMatch(executionPanel, /Number\(|parseFloat|parseInt/);
assert.doesNotMatch(executionPanel, /dangerouslySetInnerHTML|innerHTML/);

assert.match(page, /CalculationWorkspace/);
assert.match(page, /Sektör motoru yalnız API allowlist’inden seçilir/);

console.log("Calculation workspace security contract: PASS");
