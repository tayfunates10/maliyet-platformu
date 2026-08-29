import { expect, test } from "@playwright/test";
import {
  degradedBaselineDashboard,
  emptyDashboard,
  loadedDashboard,
  LOGIN_TOKEN,
  mismatchedTenantDashboard,
  ORGANIZATION_ID,
  ORGANIZATION_LIST,
  unavailableBaselineDashboard,
} from "./fixtures/dashboard-fixtures.mjs";

const DASHBOARD_PATH = `**/api/management/organizations/${ORGANIZATION_ID}/dashboard`;

/**
 * Stub the management proxy boundary only.
 *
 * Everything below the proxy (engines, rules, database) is exercised by the
 * API's own suite; here the point is that a known payload renders exactly the
 * figures it contains, and that a missing or broken payload renders an honest
 * state rather than a placeholder.
 */
async function stubManagementApi(page, { dashboard, dashboardStatus = 200 } = {}) {
  await page.route("**/api/management/auth/login", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ token_type: "bearer", access_token: LOGIN_TOKEN }),
    }),
  );
  await page.route("**/api/management/organizations?*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(ORGANIZATION_LIST),
    }),
  );
  await page.route(DASHBOARD_PATH, (route) =>
    route.fulfill({
      status: dashboardStatus,
      contentType: "application/json",
      body: JSON.stringify(dashboard ?? { detail: "unavailable" }),
    }),
  );
}

async function signIn(page) {
  await page.goto("/dashboard");
  await page.getByLabel("E-posta").fill("uye@example.test");
  await page.getByLabel("Parola").fill("gecerli-parola-1234");
  await page.getByRole("button", { name: "Oturum aç" }).click();
}

/** Next.js injects its own role="alert" route announcer; match ours by text. */
function panelAlert(page, text) {
  return page.getByRole("alert").filter({ hasText: text });
}

/**
 * The sidebar is a drawer below 900px. While closed it is `visibility: hidden`,
 * which deliberately removes it from the accessibility tree, so a role query
 * cannot see it until the drawer is opened.
 */
async function revealNavigation(page) {
  const toggle = page.getByRole("button", { name: /Menü/ });
  if (await toggle.isVisible()) await toggle.click();
  const nav = page.getByRole("navigation", { name: "Ana gezinme" });
  await expect(nav).toBeVisible();
  return nav;
}

const FOOD_OPTION = "Tahin Helva 400g Parti Maliyeti · s4";
const TRANSPORT_OPTION = "Konya-Istanbul Sefer Maliyeti · s1";

test.describe("gösterge paneli", () => {
  test("kayıtlı sürüm değerlerini olduğu gibi gösterir", async ({ page }, testInfo) => {
    await stubManagementApi(page, { dashboard: loadedDashboard() });
    await signIn(page);

    const metrics = page.getByRole("region", { name: "Temel göstergeler" });
    await expect(metrics).toBeVisible();

    await page.getByLabel("Hesaplama").selectOption({ label: TRANSPORT_OPTION });
    // The transportation engine's own trip total, formatted for tr-TR.
    await expect(metrics).toContainText("₺25.585,34");
    // The exact Decimal is shown next to it and keeps every digit.
    await expect(metrics).toContainText("31.58684074074074074074074074");
    // The rule base is fully effective.
    await expect(metrics).toContainText("3 / 3");
    await expect(metrics.getByText("Doğrulandı")).toBeVisible();

    await expect(page.getByRole("heading", { name: "Sektörel Maliyet Girdileri" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Maliyet Dağılımı" })).toBeVisible();

    await testInfo.attach(`dashboard-${testInfo.project.name}.png`, {
      body: await page.screenshot({ fullPage: true }),
      contentType: "image/png",
    });
  });

  test("motorun yayınlamadığı metrik sıfır değil, boş gösterilir", async ({ page }) => {
    await stubManagementApi(page, { dashboard: loadedDashboard() });
    await signIn(page);

    await page.getByLabel("Hesaplama").selectOption({ label: FOOD_OPTION });

    const metrics = page.getByRole("region", { name: "Temel göstergeler" });
    // The food engine publishes neither a grand total nor a margin ratio.
    await expect(metrics.getByText("Bu motor bu değeri yayınlamıyor")).toHaveCount(2);
    await expect(metrics).not.toContainText("₺0,00");
    // Its unit cost is still shown at full precision.
    await expect(metrics).toContainText("63.03322847457627118644067797");
  });

  test("hesaplaması olmayan tenant boş durum gösterir", async ({ page }, testInfo) => {
    await stubManagementApi(page, { dashboard: emptyDashboard() });
    await signIn(page);

    await expect(page.getByText("Sektörel maliyet girdisi yok")).toBeVisible();
    await expect(page.getByText("Henüz karar senaryosu yok")).toBeVisible();
    await expect(page.getByText("Henüz yayınlanmış widget yok")).toBeVisible();
    // Not a spinner and not a zero.
    await expect(page.getByText("Henüz yeterli veri yok").first()).toBeVisible();
    await expect(page.getByRole("region", { name: "Temel göstergeler" })).not.toContainText("₺0,00");

    await testInfo.attach(`dashboard-empty-${testInfo.project.name}.png`, {
      body: await page.screenshot({ fullPage: true }),
      contentType: "image/png",
    });
  });

  test("çözülemeyen mevzuat kuralları temiz raporlanmaz", async ({ page }, testInfo) => {
    await stubManagementApi(page, { dashboard: degradedBaselineDashboard() });
    await signIn(page);

    const readiness = page.getByRole("region", { name: "Mevzuat Baseline" });
    await expect(readiness.getByText("Eksik/Uyarı")).toBeVisible();
    await expect(readiness).not.toContainText("Doğrulandı");
    await expect(readiness.getByText("Yürürlükte değil")).toBeVisible();
    await expect(readiness.getByText("Belirsiz")).toBeVisible();
    await expect(readiness).toContainText("no effective version");
    await expect(readiness).toContainText("1 / 3");

    await testInfo.attach(`readiness-degraded-${testInfo.project.name}.png`, {
      body: await page.screenshot({ fullPage: true }),
      contentType: "image/png",
    });
  });

  test("doğrulanamayan baseline hata olarak gösterilir", async ({ page }) => {
    await stubManagementApi(page, { dashboard: unavailableBaselineDashboard() });
    await signIn(page);

    const readiness = page.getByRole("region", { name: "Mevzuat Baseline" });
    await expect(readiness.getByText("Baseline doğrulanamadı")).toBeVisible();
    await expect(readiness).not.toContainText("Doğrulandı");
    await expect(readiness).toContainText("baseline manifest unreadable");
  });

  test("API hatasında panel çökmez, yeniden deneme sunar", async ({ page }) => {
    await stubManagementApi(page, { dashboardStatus: 500 });
    await signIn(page);

    const error = panelAlert(page, "Veriler yüklenemedi");
    await expect(error).toBeVisible();
    await expect(page.getByRole("button", { name: "Tekrar dene" })).toBeVisible();
    // The shell survives a failed request: the heading stays and navigation is
    // still reachable at whatever viewport this project runs.
    await expect(page.getByRole("heading", { name: "Üretim Maliyet Analizi" })).toBeVisible();
    await revealNavigation(page);
  });

  test("başka tenant'a ait projeksiyon reddedilir", async ({ page }) => {
    await stubManagementApi(page, { dashboard: mismatchedTenantDashboard() });
    await signIn(page);

    // The client proves the projection belongs to the requested tenant.
    await expect(panelAlert(page, "Sunucu yanıtı")).toBeVisible();
    await expect(page.locator("body")).not.toContainText("₺25.585,34");
  });

  test("sayfa yatay taşma üretmez", async ({ page }) => {
    await stubManagementApi(page, { dashboard: loadedDashboard() });
    await signIn(page);
    await page.getByRole("heading", { name: "Sektörel Maliyet Girdileri" }).waitFor();

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBe(0);
  });
});

test.describe("gezinme", () => {
  test("var olmayan bölümler devre dışıdır", async ({ page }) => {
    await stubManagementApi(page, { dashboard: loadedDashboard() });
    await signIn(page);

    const nav = await revealNavigation(page);
    await expect(nav.getByRole("link", { name: "Gösterge Paneli" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    for (const label of ["Mevzuat Baseline", "Raporlar", "Ayarlar"]) {
      await expect(nav.getByRole("button", { name: label })).toBeDisabled();
    }
    for (const [label, href] of [
      ["Maliyet Hesaplamaları", "/calculations"],
      ["Karar Analizi", "/decision-analysis"],
      ["Widget Markalama", "/widget-branding"],
    ]) {
      await expect(nav.getByRole("link", { name: label })).toHaveAttribute("href", href);
    }
  });
});
