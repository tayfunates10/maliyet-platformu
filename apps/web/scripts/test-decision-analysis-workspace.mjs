import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { preserveSuccessfulPrimaryResult } from "../lib/decision-analysis-workspace-flow.ts";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const apiClient = readFileSync(resolve(webRoot, "lib/decision-analysis-api.ts"), "utf8");
const workspace = readFileSync(resolve(webRoot, "components/decision-analysis-workspace.tsx"), "utf8");
const proxy = readFileSync(resolve(webRoot, "app/api/management/[...path]/route.ts"), "utf8");
const page = readFileSync(resolve(webRoot, "app/decision-analysis/page.tsx"), "utf8");

for (const source of [apiClient, workspace, proxy]) {
  assert.doesNotMatch(source, /localStorage|sessionStorage|indexedDB|document\.cookie/);
  assert.doesNotMatch(source, /console\.(?:log|debug|info|warn|error)/);
}

assert.match(apiClient, /const MANAGEMENT_PREFIX = "\/api\/management"/);
assert.match(apiClient, /decision-analysis\/investment-scenarios/);
assert.match(apiClient, /Authorization: `Bearer \$\{token\}`/);
assert.match(apiClient, /credentials:\s*"omit"/);
assert.match(apiClient, /cache:\s*"no-store"/);
assert.match(apiClient, /redirect:\s*"error"/);
assert.match(apiClient, /referrerPolicy:\s*"no-referrer"/);
assert.match(apiClient, /scenarios\.length !== 3/);
assert.match(apiClient, /scenarios\[0\]\?\.key !== "pessimistic"/);
assert.match(apiClient, /scenarios\[1\]\?\.key !== "normal"/);
assert.match(apiClient, /scenarios\[2\]\?\.key !== "optimistic"/);
assert.match(apiClient, /const SHA256_PATTERN = \/\^\[0-9a-f\]\{64\}\$\//);
assert.match(apiClient, /requireDigest\(payload, "input_sha256"\)/);
assert.match(apiClient, /requireDigest\(payload, "output_sha256"\)/);
assert.match(apiClient, /listDecisionAnalysisHistory/);
assert.match(apiClient, /getDecisionAnalysisArtifact/);
assert.match(apiClient, /\?limit=\$\{HISTORY_PAGE_SIZE\}&offset=0/);
assert.match(apiClient, /payload\.length > HISTORY_PAGE_SIZE/);
assert.doesNotMatch(apiClient, /parseFloat|parseInt|Number\(/);
assert.doesNotMatch(apiClient, /fetch\(\s*["'`]https?:\/\//);

assert.match(proxy, /organizations\/\$\{UUID\}\/decision-analysis\/investment-scenarios/);
assert.match(proxy, /investment-scenarios\/\$\{UUID\}/);
assert.match(proxy, /authenticated:\s*true/);
assert.match(proxy, /allowDeploymentPagination:\s*true/);
assert.match(proxy, /authorization\.startsWith\("Bearer "\)/);
assert.match(proxy, /MAX_BODY_BYTES = 16_384/);
assert.doesNotMatch(proxy, /Access-Control-Allow-Origin/);
assert.doesNotMatch(proxy, /\^.*\.\*.*\$/);

assert.match(workspace, /type="password"/);
assert.match(workspace, /setPassword\(""\)/);
assert.match(workspace, /setToken\(null\)/);
assert.match(workspace, /await logoutWorkspace\(token\)/);
assert.match(workspace, /runDecisionAnalysis/);
assert.match(workspace, /listDecisionAnalysisHistory/);
assert.match(workspace, /getDecisionAnalysisArtifact/);
assert.match(workspace, /Doğrula ve aç/);
assert.match(workspace, /engine yeniden çalıştırılmadı/);
assert.match(workspace, /Input SHA-256/);
assert.match(workspace, /Output SHA-256/);
assert.match(workspace, /"pessimistic"/);
assert.match(workspace, /"normal"/);
assert.match(workspace, /"optimistic"/);
assert.match(workspace, /exactRatio/);
assert.match(workspace, /Oturum açıldı; analiz geçmişi bu istekte yüklenemedi\. Oturum korunuyor\./);
assert.match(workspace, /Karar analizi kaydedildi; geçmiş listesi bu istekte yenilenemedi/);
const tokenCommit = workspace.indexOf("setToken(nextToken)");
const initialHistoryFetch = workspace.indexOf("listDecisionAnalysisHistory(nextToken, nextOrganizationId)");
assert.ok(tokenCommit >= 0 && initialHistoryFetch > tokenCommit, "session must be committed before optional history refresh");
assert.doesNotMatch(workspace, /parseFloat|parseInt|Number\(|Intl\.NumberFormat/);
assert.doesNotMatch(workspace, /dangerouslySetInnerHTML|innerHTML|eval|Function\(/);
assert.doesNotMatch(workspace, /(?:value|defaultValue|data-[\w-]+|aria-[\w-]+)=\{token\}|>\s*\{token\}\s*</);

const retainedSession = await preserveSuccessfulPrimaryResult(
  async () => Object.freeze({ token: "opaque-session", organizationId: "tenant-a" }),
  async () => {
    throw new Error("history unavailable");
  },
);
assert.equal(retainedSession.refreshed, false);
assert.equal(retainedSession.result.token, "opaque-session");
assert.equal(retainedSession.result.organizationId, "tenant-a");

let createCount = 0;
const retainedCreation = await preserveSuccessfulPrimaryResult(
  async () => {
    createCount += 1;
    return Object.freeze({ artifactId: "artifact-1" });
  },
  async () => {
    throw new Error("history refresh unavailable");
  },
);
assert.equal(createCount, 1, "history refresh failure must not rerun immutable artifact creation");
assert.equal(retainedCreation.refreshed, false);
assert.equal(retainedCreation.result.artifactId, "artifact-1");

assert.match(page, /DecisionAnalysisWorkspace/);
assert.match(page, /server-side Decimal motorundan gelir/);
assert.match(page, /vergi oranı, finansman karması, enflasyon, iskonto oranı veya senaryo şoku üretmez/);

console.log("Decision analysis workspace security contract: PASS");
