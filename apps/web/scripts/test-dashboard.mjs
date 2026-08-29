import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  formatCurrency,
  formatRatioAsPercent,
  geometryPosition,
  geometryShare,
  geometryTotal,
  maxDecimalText,
  minDecimalText,
} from "../lib/decimal-format.mjs";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFileSync(resolve(webRoot, relative), "utf8");

const dashboardApi = read("lib/dashboard-api.ts");
const shell = read("components/dashboard/dashboard-shell.tsx");
const sidebar = read("components/dashboard/dashboard-sidebar.tsx");
const metricCard = read("components/dashboard/metric-card.tsx");
const sectorTable = read("components/dashboard/sector-cost-table.tsx");
const donut = read("components/dashboard/cost-distribution-chart.tsx");
const trend = read("components/dashboard/cost-trend-chart.tsx");
const readiness = read("components/dashboard/regulatory-readiness-card.tsx");
const widgetCard = read("components/dashboard/widget-preview-card.tsx");
const decisionCard = read("components/dashboard/decision-analysis-card.tsx");
const states = read("components/dashboard/dashboard-states.tsx");
const proxy = read("app/api/management/[...path]/route.ts");
const page = read("app/dashboard/page.tsx");

const dashboardSources = [
  dashboardApi,
  shell,
  sidebar,
  metricCard,
  sectorTable,
  donut,
  trend,
  readiness,
  widgetCard,
  decisionCard,
  states,
];

// --- Session and transport contract -------------------------------------

for (const source of dashboardSources) {
  assert.doesNotMatch(source, /localStorage|sessionStorage|indexedDB|document\.cookie/);
  assert.doesNotMatch(source, /console\.(?:log|debug|info|warn|error)/);
  assert.doesNotMatch(source, /dangerouslySetInnerHTML|innerHTML|eval\(|new Function\(/);
}

assert.match(dashboardApi, /const MANAGEMENT_PREFIX = "\/api\/management"/);
assert.match(dashboardApi, /credentials:\s*"omit"/);
assert.match(dashboardApi, /cache:\s*"no-store"/);
assert.match(dashboardApi, /redirect:\s*"error"/);
assert.match(dashboardApi, /referrerPolicy:\s*"no-referrer"/);
assert.match(dashboardApi, /Authorization: `Bearer \$\{token\}`/);
assert.doesNotMatch(dashboardApi, /fetch\(\s*["'`]https?:\/\//);
assert.match(proxy, /\^organizations\/\$\{UUID\}\/dashboard\$/);
assert.match(page, /DashboardShell/);

// The projection must be proven to belong to the requested tenant.
assert.match(dashboardApi, /organization\.id\.toLowerCase\(\) !== organizationId\.toLowerCase\(\)/);

// --- Financial correctness ------------------------------------------------

// No dashboard module may turn an authoritative Decimal string into a number.
for (const source of dashboardSources) {
  assert.doesNotMatch(source, /parseFloat|parseInt/);
  assert.doesNotMatch(source, /Number\((?!permille|offset)/);
}

assert.equal(formatCurrency("59.17729627118644067796610169"), "₺59,18");
assert.equal(formatRatioAsPercent("0.265"), "%26,5");
// A value far beyond double precision still formats from its exact text.
assert.equal(formatCurrency("128456230.123456789012345678901234567890"), "₺128.456.230,12");
assert.equal(formatCurrency("not-a-decimal"), null);
assert.equal(formatCurrency(null), null);

// Geometry helpers stay exact and never divide by zero.
assert.equal(geometryTotal(["148000.00", "62500.00", "18400.00", "9750.00", "27300.00"]), "265950");
assert.equal(geometryTotal(["0.000000000001", "0.000000000002"]), "0.000000000003");
assert.equal(geometryTotal([]), null);
assert.equal(geometryShare("1", "0"), 0);
assert.ok(Math.abs(geometryShare("148000.00", "265950") - 0.5565) < 0.001);
assert.equal(maxDecimalText(["59.18", "63.03", "60.10"]), "63.03");
assert.equal(minDecimalText(["59.18", "63.03", "60.10"]), "59.18");
// A flat series must sit on the mid-line rather than collapse onto an axis.
assert.equal(geometryPosition("5", "5", "5"), 0.5);
assert.equal(geometryPosition("59.18", "59.18", "63.03"), 0);
assert.equal(geometryPosition("63.03", "59.18", "63.03"), 1);

// --- No production mock data ---------------------------------------------

const FORBIDDEN_IN_RUNTIME = [
  /\bmockData\b/i,
  /\bdemoData\b/i,
  /\bsampleData\b/i,
  /\bfakeCost\b/i,
  /\bsampleDashboard\b/i,
  /\bplaceholderCost\b/i,
  /Math\.random/,
  /128456230/,
  /Demo Sanayi/,
  /Ecem Aydın/,
];

function collectRuntimeFiles(directory) {
  const collected = [];
  for (const entry of readdirSync(directory)) {
    if (entry === "node_modules" || entry === ".next" || entry === "scripts") continue;
    const full = join(directory, entry);
    if (statSync(full).isDirectory()) {
      collected.push(...collectRuntimeFiles(full));
    } else if (/\.(?:tsx?|mts|mjs)$/.test(entry) && !entry.endsWith(".d.ts")) {
      collected.push(full);
    }
  }
  return collected;
}

for (const file of [
  ...collectRuntimeFiles(resolve(webRoot, "app")),
  ...collectRuntimeFiles(resolve(webRoot, "components")),
  ...collectRuntimeFiles(resolve(webRoot, "lib")),
]) {
  const source = readFileSync(file, "utf8");
  for (const pattern of FORBIDDEN_IN_RUNTIME) {
    assert.doesNotMatch(source, pattern, `${file} must not ship placeholder dashboard data`);
  }
}

// End-to-end fixtures are test-only: nothing in the production bundle may reach
// into tests/, so the deterministic payloads can never become a UI fallback.
for (const file of [
  ...collectRuntimeFiles(resolve(webRoot, "app")),
  ...collectRuntimeFiles(resolve(webRoot, "components")),
  ...collectRuntimeFiles(resolve(webRoot, "lib")),
]) {
  const source = readFileSync(file, "utf8");
  assert.doesNotMatch(source, /["'`][^"'`]*tests\/e2e/, `${file} must not import an e2e fixture`);
  assert.doesNotMatch(source, /@playwright\/test/, `${file} must not import the test runner`);
}

// The forbidden `apiData ?? MOCK` shape must not exist anywhere in the dashboard.
for (const source of dashboardSources) {
  assert.doesNotMatch(source, /\?\?\s*(?:MOCK|FALLBACK|DEMO|SAMPLE)/i);
}

// --- Empty, error and fail-closed states ---------------------------------

assert.match(states, /PanelEmptyState/);
assert.match(states, /PanelErrorState/);
assert.match(states, /PanelSkeleton/);
// Status never rests on colour alone.
assert.match(states, /TONE_GLYPH/);
assert.match(states, /role="alert"/);
assert.match(shell, /Tekrar dene|PanelErrorState/);

// A metric the engine does not publish reads as absent, never as zero.
assert.match(metricCard, /formatted === null/);
assert.match(metricCard, /emptyText/);
assert.doesNotMatch(metricCard, /\?\?\s*0\b/);

// An absent table cell is a dash, not a zero.
assert.match(sectorTable, /NO_VALUE/);
assert.doesNotMatch(sectorTable, /amount === undefined \? "0"/);

// Readiness is fail-closed: an unverifiable baseline cannot render as clean.
assert.match(readiness, /baseline\.status === "unavailable"/);
assert.match(readiness, /Baseline doğrulanamadı/);
assert.match(dashboardApi, /baseline\.status === "ready" && baseline\.issues\.length > 0/);
assert.doesNotMatch(readiness, /%\s*100|Tam uyum/);

// Widget identifiers are never synthesised for display: the card renders no
// embed snippet, and the projection type carries no deployment identifier at
// all, so there is nothing for a placeholder to stand in for.
assert.doesNotMatch(widgetCard, /mp-widget/i);
assert.doesNotMatch(widgetCard, /<script|<iframe/i);
assert.doesNotMatch(dashboardApi, /deployment_id/);

// --- Charts ---------------------------------------------------------------

// Fixed categorical order from the validated palette, never a generated hue.
assert.match(donut, /--chart-1/);
assert.match(donut, /--chart-6/);
assert.doesNotMatch(donut, /hsl\(|Math\.random/);
// Both charts describe themselves to assistive technology.
assert.match(donut, /role="img"/);
assert.match(donut, /aria-label=/);
assert.match(trend, /role="img"/);
assert.match(trend, /aria-label=/);
// The trend states its band instead of implying a zero baseline.
assert.match(trend, /gözlenen değer aralığıdır/);
assert.match(trend, /usable\.length < 2/);

// --- Responsive floors ----------------------------------------------------

const dashboardCss = read("components/dashboard/dashboard.module.css");
// Grid and flex items must not keep a min-content floor, and a select must not
// size to its longest option: both widen the page on a narrow viewport.
assert.match(dashboardCss, /\.scopeField select \{[^}]*width: 100%/);
assert.match(dashboardCss, /\.scopeField select \{[^}]*min-width: 0/);
for (const block of ["header", "headerTitles", "scopeBar", "metricRow", "mainGrid"]) {
  assert.match(
    dashboardCss,
    new RegExp(`\\.${block} \\{[^}]*min-width: 0`),
    `.${block} must not keep a min-content width floor`,
  );
}
// The closed mobile drawer stays out of the tab order and out of scroll width.
assert.match(dashboardCss, /visibility: hidden/);
assert.match(dashboardCss, /prefers-reduced-motion/);

// --- Navigation -----------------------------------------------------------

// Routes that do not exist render disabled rather than as dead links.
assert.match(sidebar, /href: null/);
assert.match(sidebar, /className=\{styles\.navDisabled\}/);
assert.match(sidebar, /disabled/);
assert.match(sidebar, /aria-current=\{pathname === item\.href \? "page" : undefined\}/);
for (const route of ["/dashboard", "/calculations", "/decision-analysis", "/widget-branding"]) {
  assert.ok(sidebar.includes(`"${route}"`), `sidebar must link the real route ${route}`);
}

console.log("Dashboard data and security contract: PASS");
