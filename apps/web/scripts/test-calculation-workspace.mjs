import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const apiClient = readFileSync(resolve(webRoot, "lib/calculation-workspace-api.ts"), "utf8");
const workspace = readFileSync(resolve(webRoot, "components/calculation-workspace.tsx"), "utf8");
const proxy = readFileSync(resolve(webRoot, "app/api/management/[...path]/route.ts"), "utf8");
const page = readFileSync(resolve(webRoot, "app/calculations/page.tsx"), "utf8");

for (const source of [apiClient, workspace, proxy]) {
  assert.doesNotMatch(source, /localStorage|sessionStorage|indexedDB|document\.cookie/);
  assert.doesNotMatch(source, /console\.(?:log|debug|info|warn|error)/);
}

assert.match(apiClient, /const MANAGEMENT_PREFIX = "\/api\/management"/);
assert.match(apiClient, /credentials:\s*"omit"/);
assert.match(apiClient, /cache:\s*"no-store"/);
assert.match(apiClient, /redirect:\s*"error"/);
assert.match(apiClient, /referrerPolicy:\s*"no-referrer"/);
assert.match(apiClient, /headers\.set\("Authorization", `Bearer \$\{options\.token\}`\)/);
assert.match(apiClient, /listWorkspaceOrganizations/);
assert.match(apiClient, /listWorkspaceEngines/);
assert.match(apiClient, /listCalculations/);
assert.match(apiClient, /createCalculation/);
assert.match(apiClient, /calculation\.organization_id !== organizationId/);
assert.match(apiClient, /seenIds/);
assert.doesNotMatch(apiClient, /fetch\(\s*["'`]https?:\/\//);

assert.match(proxy, /\^engines\$/);
assert.match(proxy, /organizations\/\$\{UUID\}\/calculations/);
assert.match(proxy, /allowDeploymentPagination:\s*true/);
assert.match(proxy, /authorization\.startsWith\("Bearer "\)/);
assert.doesNotMatch(proxy, /Access-Control-Allow-Origin/);

assert.match(workspace, /type="password"/);
assert.match(workspace, /setPassword\(""\)/);
assert.match(workspace, /setToken\(null\)/);
assert.match(workspace, /Promise\.all/);
assert.match(workspace, /WRITE_ROLES/);
assert.match(workspace, /listCalculations/);
assert.match(workspace, /createCalculation/);
assert.doesNotMatch(workspace, /useEffect/);
assert.doesNotMatch(workspace, /\{token\}/);

assert.match(page, /CalculationWorkspace/);
assert.match(page, /Sektör motoru yalnız API allowlist’inden seçilir/);

console.log("Calculation workspace security contract: PASS");
