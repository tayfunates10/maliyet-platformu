import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const apiClient = readFileSync(resolve(webRoot, "lib/widget-branding-management-api.ts"), "utf8");
const manager = readFileSync(resolve(webRoot, "components/widget-branding-manager.tsx"), "utf8");
const managementPage = readFileSync(resolve(webRoot, "app/widget-branding/page.tsx"), "utf8");
const managementProxy = readFileSync(
  resolve(webRoot, "app/api/management/[...path]/route.ts"),
  "utf8",
);

for (const source of [apiClient, manager, managementProxy]) {
  assert.doesNotMatch(source, /localStorage/);
  assert.doesNotMatch(source, /sessionStorage/);
  assert.doesNotMatch(source, /indexedDB/);
  assert.doesNotMatch(source, /document\.cookie/);
  assert.doesNotMatch(source, /console\.(?:log|debug|info|warn|error)/);
}

assert.match(apiClient, /const MANAGEMENT_PREFIX = "\/api\/management"/);
assert.match(apiClient, /credentials:\s*"omit"/);
assert.match(apiClient, /cache:\s*"no-store"/);
assert.match(apiClient, /redirect:\s*"error"/);
assert.match(apiClient, /referrerPolicy:\s*"no-referrer"/);
assert.match(apiClient, /headers\.set\("Authorization", `Bearer \$\{options\.token\}`\)/);
assert.doesNotMatch(apiClient, /response\.text\s*\(/);
assert.doesNotMatch(apiClient, /response\.statusText/);
assert.doesNotMatch(apiClient, /fetch\(\s*["'`]https?:\/\//);
assert.match(apiClient, /origin\.startsWith\("https:\/\/"\)/);

assert.match(apiClient, /"\/auth\/login"/);
assert.match(apiClient, /"\/organizations"/);
assert.match(apiClient, /listWidgetDeployments/);
assert.match(apiClient, /widget-deployments`/);
assert.match(apiClient, /publishable/);
assert.match(apiClient, /source_revoked_at/);
assert.match(apiClient, /widget-branding-profiles/);
assert.match(apiClient, /widget-deployments\/\$\{encodeURIComponent\(deploymentId\)\}\/presentation/);
assert.match(apiClient, /body:\s*\{ branding_profile_id: profileId \}/);
assert.match(apiClient, /UUID_PATTERN/);

assert.match(managementProxy, /getPublicApiBaseUrl/);
assert.match(managementProxy, /parsed\.protocol === "https:"/);
assert.match(managementProxy, /parsed\.protocol === "http:" && loopback/);
assert.match(managementProxy, /const ROUTE_RULES/);
assert.match(managementProxy, /\^auth\\\/login\$/);
assert.match(managementProxy, /\^organizations\$/);
assert.match(managementProxy, /widget-branding-profiles/);
assert.match(managementProxy, /widget-deployments/);
assert.match(managementProxy, /widget-deployments\/\$\{UUID\}\/presentation/);
assert.match(managementProxy, /request\.nextUrl\.search !== ""/);
assert.match(managementProxy, /MAX_BODY_BYTES = 16_384/);
assert.match(managementProxy, /authorization\.startsWith\("Bearer "\)/);
assert.match(managementProxy, /authorization not accepted on login/);
assert.match(managementProxy, /"Cache-Control": "no-store"/);
assert.match(managementProxy, /"X-Content-Type-Options": "nosniff"/);
assert.doesNotMatch(managementProxy, /allow_origins|Access-Control-Allow-Origin/);
assert.doesNotMatch(managementProxy, /headers\.get\("cookie"\)/i);
assert.doesNotMatch(managementProxy, /headers\.get\("origin"\)/i);
assert.doesNotMatch(managementProxy, /headers\.get\("referer"\)/i);

assert.match(manager, /type="password"/);
assert.match(manager, /setPassword\(""\)/);
assert.match(manager, /setToken\(null\)/);
assert.doesNotMatch(manager, /\{token\}/);
assert.doesNotMatch(manager, /useEffect/);
assert.match(manager, /const \[dirty, setDirty\] = useState\(false\)/);
assert.match(manager, /const \[confirmPublish, setConfirmPublish\] = useState\(false\)/);
assert.match(manager, /const \[deployments, setDeployments\]/);
assert.match(manager, /listWidgetDeployments\s*\(/);
assert.match(manager, /Promise\.all/);
assert.match(manager, /selectedDeployment/);
assert.match(manager, /selectedDeployment\.publishable/);
assert.match(manager, /disabled=\{!deployment\.publishable\}/);
assert.match(manager, /Deployment seçin/);
assert.doesNotMatch(manager, /Widget deployment UUID/);
assert.doesNotMatch(manager, /placeholder="[0-9a-f-]{36}"/i);
assert.match(manager, /if \(dirty\)/);
assert.match(manager, /if \(!confirmPublish\)/);
assert.match(manager, /Canlı presentation'ı yayınla/);
assert.match(manager, /Kaydetme işlemi canlı widget'ı değiştirmez/);

const saveStart = manager.indexOf("async function handleSave");
const publishStart = manager.indexOf("async function handlePublish");
assert.ok(saveStart >= 0 && publishStart > saveStart, "save/publish handlers must remain explicit");
const saveBody = manager.slice(saveStart, publishStart);
assert.doesNotMatch(
  saveBody,
  /publishBrandingProfile\s*\(/,
  "saving a draft must never implicitly publish it",
);
const publishBody = manager.slice(publishStart, manager.indexOf("function logout", publishStart));
assert.match(publishBody, /publishBrandingProfile\s*\(/);
assert.match(publishBody, /confirmPublish/);
assert.match(publishBody, /dirty/);
assert.match(publishBody, /selectedDeployment/);
assert.match(publishBody, /publishable/);

assert.match(managementPage, /WidgetBrandingManager/);
assert.match(managementPage, /Taslak kaydetme ve canlı presentation yayınlama ayrı işlemlerdir/);

console.log("Widget branding management security contract: PASS");
