import { readFileSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const packageJson = JSON.parse(readFileSync(resolve(root, "package.json"), "utf8"));

const requiredFiles = [
  "app/layout.tsx",
  "app/page.tsx",
  "app/globals.css",
  "lib/sectors.ts",
  "lib/runtime-config.ts",
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

const nextConfig = readFileSync(resolve(root, "next.config.mjs"), "utf8");
if (!nextConfig.includes("useTypeScriptCli: true")) {
  throw new Error("Next.js must use the TypeScript CLI for TypeScript 7 compatibility");
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
