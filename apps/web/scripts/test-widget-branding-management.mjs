import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const apiClient = readFileSync(resolve(webRoot, "lib/widget-branding-management-api.ts"), "utf8");
const manager = readFileSync(resolve(webRoot, "components/widget-branding-manager.tsx"), "utf8");
const managementPage = readFileSync(resolve(webRoot, "app/widget-branding/page.tsx"), "utf8");

for (const source of [apiClient, manager]) {
  assert.doesNotMatch(source, /localStorage/);
  assert.doesNotMatch(source, /sessionStorage/);
  assert.doesNotMatch(source, /indexedDB/);
  assert.doesNotMatch(source, /document\.cookie/);
  assert.doesNotMatch(source, /console\.(?:log|debug|info|warn|error)/);
}

assert.match(apiClient, /parsed\.protocol === "https:"/);
assert.match(apiClient, /parsed\.protocol === "http:" && loopback/);
assert.match(apiClient, /credentials:\s*"omit"/);
assert.match(apiClient, /cache:\s*"no-store"/);
assert.match(apiClient, /redirect:\s*"error"/);
assert.match(apiClient, /referrerPolicy:\s*"no-referrer"/);
assert.match(apiClient, /headers\.set\("Authorization", `Bearer \$\{options\.token\}`\)/);
assert.doesNotMatch(apiClient, /response\.text\s*\(/);
assert.doesNotMatch(apiClient, /response\.statusText/);

assert.match(apiClient, /"\/auth\/login"/);
assert.match(apiClient, /"\/organizations\?limit=100&offset=0"/);
assert.match(apiClient, /widget-branding-profiles\?limit=100&offset=0/);
assert.match(apiClient, /widget-branding-profiles`/);
assert.match(apiClient, /widget-deployments\/\$\{encodeURIComponent\(deploymentId\)\}\/presentation/);
assert.match(apiClient, /body:\s*\{ branding_profile_id: profileId \}/);
assert.match(apiClient, /UUID_PATTERN/);

assert.match(manager, /type="password"/);
assert.match(manager, /setPassword\(""\)/);
assert.match(manager, /setToken\(null\)/);
assert.doesNotMatch(manager, /\{token\}/);
assert.doesNotMatch(manager, /useEffect/);
assert.match(manager, /const \[dirty, setDirty\] = useState\(false\)/);
assert.match(manager, /const \[confirmPublish, setConfirmPublish\] = useState\(false\)/);
assert.match(manager, /if \(dirty\)/);
assert.match(manager, /if \(!confirmPublish\)/);
assert.match(manager, /!isDeploymentId\(deploymentId\)/);
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

assert.match(managementPage, /WidgetBrandingManager/);
assert.match(managementPage, /Taslak kaydetme ve canlı presentation yayınlama ayrı işlemlerdir/);

console.log("Widget branding management security contract: PASS");
