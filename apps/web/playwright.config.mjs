import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end configuration for the management surface.
 *
 * The suite drives the real Next.js production build and stubs only the
 * management proxy boundary, so no database or API process is needed and the
 * screenshots are deterministic. `API_BASE_URL` still has to satisfy the
 * runtime contract even though no request reaches it.
 */
const PORT = Number(process.env.PLAYWRIGHT_PORT ?? 3100);

export default defineConfig({
  testDir: "./tests/e2e",
  outputDir: "./tests/e2e/.artifacts",
  snapshotDir: "./tests/e2e/screenshots",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? [["line"]] : [["list"]],
  timeout: 45_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    locale: "tr-TR",
    timezoneId: "Europe/Istanbul",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "mobile", use: { ...devices["Pixel 7"], viewport: { width: 390, height: 844 } } },
  ],
  webServer: {
    command: `npx next start --port ${PORT} --hostname 127.0.0.1`,
    url: `http://127.0.0.1:${PORT}/dashboard`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: { API_BASE_URL: "https://api.example.invalid", NEXT_TELEMETRY_DISABLED: "1" },
  },
});
