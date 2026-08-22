import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const packageJson = JSON.parse(readFileSync(resolve(root, "package.json"), "utf8"));

const requiredFiles = [
  "app/layout.tsx",
  "app/page.tsx",
  "app/globals.css",
  "app/api/management/[...path]/route.ts",
  "app/widget-branding/page.tsx",
  "app/widget-branding/page.module.css",
  "components/widget-branding-manager.tsx",
  "components/widget-branding-manager.module.css",
  "lib/sectors.ts",
  "lib/runtime-config.ts",
  "lib/widget-branding-management-api.ts",
  "public/widget/v1.0.0/loader.js",
  "public/widget/v1.1.0/loader.js",
  "public/widget/v1.1.0/styles.css",
  "public/widget/v1.2.0/loader.js",
  "public/widget/v1.2.0/styles.css",
  "scripts/test-widget-loader.mjs",
  "scripts/test-widget-theme-config.mjs",
  "scripts/test-widget-published-branding.mjs",
  "scripts/test-widget-branding-management.mjs",
  "biome.json",
  "tsconfig.json",
  ".env.example",
];

const missingFiles = requiredFiles.filter((path) => !existsSync(resolve(root, path)));
if (missingFiles.length > 0) {
  throw new Error(`Missing web contract files: ${missingFiles.join(", ")}`);
}

const dependencyGroups = [packageJson.dependencies, packageJson.devDependencies];
for (const dependencies of dependencyGroups) {
  for (const [name, version] of Object.entries(dependencies)) {
    if (/^[~^><=*]/.test(version)) {
      throw new Error(`Dependency ${name} must use an exact version, found ${version}`);
    }
  }
}

if (packageJson.engines.node !== ">=24.0.0 <25") {
  throw new Error("Web runtime must remain on the documented Node 24 LTS line");
}

if (packageJson.devDependencies.typescript !== "7.0.2") {
  throw new Error("Web type checking must remain on the reviewed TypeScript 7 CLI version");
}

if (packageJson.devDependencies["@biomejs/biome"] !== "2.5.6") {
  throw new Error("Web linting must remain on the reviewed Biome version");
}

if (
  packageJson.scripts["widget:test"] !==
  "node scripts/test-widget-loader.mjs && node scripts/test-widget-theme-config.mjs && node scripts/test-widget-published-branding.mjs"
) {
  throw new Error("All published Widget SDK security contract tests must run in CI");
}

if (packageJson.scripts["management:test"] !== "node scripts/test-widget-branding-management.mjs") {
  throw new Error("Authenticated widget branding management contract must run in CI");
}

const nextConfig = readFileSync(resolve(root, "next.config.mjs"), "utf8");
if (!nextConfig.includes("useTypeScriptCli: true")) {
  throw new Error("Next.js must use the TypeScript CLI for TypeScript 7 compatibility");
}

const widgetV100 = readFileSync(resolve(root, "public/widget/v1.0.0/loader.js"), "utf8");
if (!widgetV100.includes('const SDK_VERSION = "1.0.0"')) {
  throw new Error("Widget v1.0.0 asset must self-identify as version 1.0.0");
}

const widgetV110 = readFileSync(resolve(root, "public/widget/v1.1.0/loader.js"), "utf8");
if (!widgetV110.includes('const SDK_VERSION = "1.1.0"')) {
  throw new Error("Widget v1.1.0 asset must self-identify as version 1.1.0");
}

const widgetV120 = readFileSync(resolve(root, "public/widget/v1.2.0/loader.js"), "utf8");
if (!widgetV120.includes('const SDK_VERSION = "1.2.0"')) {
  throw new Error("Widget v1.2.0 asset must self-identify as version 1.2.0");
}

const sectorsSource = readFileSync(resolve(root, "lib/sectors.ts"), "utf8");
const lockedSectorSlugs = [
  "food-manufacturing",
  "textile-manufacturing",
  "basic-metals",
  "e-commerce",
  "commerce",
  "transportation",
  "accommodation",
  "tourism",
];
for (const slug of lockedSectorSlugs) {
  if (!sectorsSource.includes(`slug: "${slug}"`)) {
    throw new Error(`Locked sector missing from web shell: ${slug}`);
  }
}

console.log("Web contract: PASS");
