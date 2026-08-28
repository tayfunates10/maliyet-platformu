"use client";

import Link from "next/link";
import { type FormEvent, useCallback, useEffect, useState } from "react";
import {
  listWorkspaceOrganizations,
  loginWorkspace,
  logoutWorkspace,
  type WorkspaceOrganization,
} from "@/lib/calculation-workspace-api";
import { type DashboardOverview, fetchDashboard } from "@/lib/dashboard-api";
import { formatCurrency, formatDateTime, formatInteger, formatRatioAsPercent } from "@/lib/decimal-format.mjs";
import { CostDistributionChart } from "./cost-distribution-chart";
import { CostTrendChart } from "./cost-trend-chart";
import { DashboardSidebar } from "./dashboard-sidebar";
import { ChartSkeleton, PanelErrorState, PanelSkeleton, StatusPill } from "./dashboard-states";
import { DecisionAnalysisCard } from "./decision-analysis-card";
import { MetricCard } from "./metric-card";
import { RegulatoryReadinessCard } from "./regulatory-readiness-card";
import { SectorCostTable } from "./sector-cost-table";
import styles from "./dashboard.module.css";
import { WidgetPreviewCard } from "./widget-preview-card";

type LoadState = "idle" | "loading" | "loaded" | "error";

function friendlyError(error: unknown): string {
  if (error instanceof Error) {
    if (error.message === "authentication_required") return "Oturum doğrulanamadı.";
    if (error.message === "access_denied") return "Bu organizasyon için erişim yetkiniz yok.";
    if (error.message === "not_found") return "Organizasyon bulunamadı.";
    if (error.message === "invalid_response") return "Sunucu yanıtı doğrulamadan geçmedi.";
  }
  return "Veriler alınamadı. Bağlantıyı kontrol edip tekrar deneyin.";
}

/**
 * The dashboard's only stateful component.
 *
 * The session token stays in memory and is never written to browser storage, in
 * line with the other management screens. Every figure rendered below comes
 * from one tenant-scoped request; when the request fails or returns nothing,
 * the panels render an explicit error or empty state rather than a placeholder
 * dataset.
 */
export function DashboardShell() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [organizations, setOrganizations] = useState<readonly WorkspaceOrganization[]>([]);
  const [organizationId, setOrganizationId] = useState("");
  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [state, setState] = useState<LoadState>("idle");
  const [errorText, setErrorText] = useState("");
  const [busy, setBusy] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [selectedCalculationId, setSelectedCalculationId] = useState("");

  const load = useCallback(async (activeToken: string, activeOrganizationId: string) => {
    setState("loading");
    setErrorText("");
    try {
      const next = await fetchDashboard(activeToken, activeOrganizationId);
      setOverview(next);
      setSelectedCalculationId(next.calculations[0]?.calculation_id ?? "");
      setState("loaded");
    } catch (error) {
      setOverview(null);
      setErrorText(friendlyError(error));
      setState("error");
    }
  }, []);

  useEffect(() => {
    if (token === null || organizationId === "") return;
    void load(token, organizationId);
  }, [token, organizationId, load]);

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setErrorText("");
    try {
      const nextToken = await loginWorkspace(email.trim(), password);
      setPassword("");
      const nextOrganizations = await listWorkspaceOrganizations(nextToken);
      setToken(nextToken);
      setOrganizations(nextOrganizations);
      setOrganizationId(nextOrganizations[0]?.id ?? "");
      if (nextOrganizations.length === 0) setState("loaded");
    } catch (error) {
      setToken(null);
      setOrganizations([]);
      setPassword("");
      setErrorText(friendlyError(error));
    } finally {
      setBusy(false);
    }
  }

  async function handleSignOut() {
    if (token === null) return;
    setBusy(true);
    try {
      await logoutWorkspace(token);
    } catch {
      // The local session is dropped either way; a failed revoke must not strand the UI.
    } finally {
      setToken(null);
      setOrganizations([]);
      setOrganizationId("");
      setOverview(null);
      setState("idle");
      setBusy(false);
    }
  }

  if (token === null) {
    return (
      <div className={styles.loginWrap}>
        <div className={styles.loginCard}>
          <h1>Gösterge paneli oturumu</h1>
          <p className={styles.panelHint}>
            Panel yalnız kimliği doğrulanmış üyenin kendi organizasyon verisini gösterir. Oturum
            token’ı tarayıcı depolamasına yazılmaz.
          </p>
          <form className={styles.loginForm} onSubmit={handleLogin}>
            <label>
              E-posta
              <input
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </label>
            <label>
              Parola
              <input
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            <button type="submit" disabled={busy}>
              {busy ? "Bağlanıyor…" : "Oturum aç"}
            </button>
          </form>
          {errorText === "" ? null : (
            <p role="alert" className={styles.stateError} style={{ margin: 0 }}>
              {errorText}
            </p>
          )}
        </div>
      </div>
    );
  }

  const selected =
    overview?.calculations.find((item) => item.calculation_id === selectedCalculationId) ??
    overview?.calculations[0] ??
    null;
  const baseline = overview?.regulatory_baseline ?? null;
  const loading = state === "loading";
  // One series, one measure, one engine: versions of different engines are
  // different financial objects and must never share an axis.
  const selectedTimeline = (overview?.timeline ?? []).filter(
    (entry) => entry.calculation_id === selected?.calculation_id,
  );

  return (
    <div className={styles.shell}>
      <DashboardSidebar
        organization={overview?.organization ?? null}
        open={sidebarOpen}
        onNavigate={() => setSidebarOpen(false)}
        onSignOut={() => void handleSignOut()}
        busy={busy}
      />

      <main className={styles.content}>
        <header className={styles.header}>
          <div className={styles.headerTitles}>
            <button
              type="button"
              className={styles.sidebarToggle}
              onClick={() => setSidebarOpen((current) => !current)}
              aria-expanded={sidebarOpen}
            >
              ☰ Menü
            </button>
            <h1>Üretim Maliyet Analizi</h1>
            <p className={styles.headerLead}>
              Sektör motorlarının kaydettiği değişmez hesaplama sürümleri, sürümlenmiş TR mevzuat
              kural tabanı ve tenant sınırları içindeki karar/widget durumu.
            </p>
          </div>
          <div className={styles.headerActions}>
            <Link className={styles.primaryAction} href="/calculations">
              + Yeni Hesaplama
            </Link>
            <button
              type="button"
              className={styles.ghostAction}
              disabled
              title="Rapor dışa aktarma bir hesaplama sürümü üzerinden yapılır; hesaplama çalışma alanını kullanın"
            >
              Dışa Aktar
            </button>
          </div>
        </header>

        <div className={styles.scopeBar}>
          <label className={styles.scopeField}>
            Organizasyon
            <select
              value={organizationId}
              onChange={(event) => setOrganizationId(event.target.value)}
              disabled={busy || organizations.length === 0}
            >
              {organizations.map((organization) => (
                <option key={organization.id} value={organization.id}>
                  {organization.legal_name} · {organization.role}
                </option>
              ))}
            </select>
          </label>
          <label className={styles.scopeField}>
            Hesaplama
            <select
              value={selectedCalculationId}
              onChange={(event) => setSelectedCalculationId(event.target.value)}
              disabled={loading || (overview?.calculations.length ?? 0) === 0}
            >
              {(overview?.calculations ?? []).map((item) => (
                <option key={item.calculation_id} value={item.calculation_id}>
                  {item.name}
                  {item.version_number === null ? "" : ` · s${item.version_number}`}
                </option>
              ))}
            </select>
          </label>
          {overview === null ? null : (
            <span className={styles.scopeMeta}>
              Son güncelleme: {formatDateTime(overview.generated_at) ?? "—"}
            </span>
          )}
        </div>

        {state === "error" ? (
          <PanelErrorState
            description={errorText}
            busy={loading}
            onRetry={() => {
              if (token !== null && organizationId !== "") void load(token, organizationId);
            }}
          />
        ) : null}

        <section className={styles.metricRow} aria-label="Temel göstergeler">
          {loading || selected === null ? (
            ["toplam", "birim", "marj", "mevzuat"].map((slot) => (
              <div key={`metric-skeleton-${slot}`} className={styles.metricCard}>
                <PanelSkeleton lines={2} />
              </div>
            ))
          ) : (
            <>
              <MetricCard
                label="Toplam Maliyet"
                formatted={formatCurrency(selected.total_cost)}
                exact={selected.total_cost}
                support={selected.engine_title ?? selected.calculation_type}
              />
              <MetricCard
                label="Birim Maliyet"
                formatted={formatCurrency(selected.unit_cost)}
                exact={selected.unit_cost}
                support={
                  selected.version_number === null
                    ? undefined
                    : `Sürüm ${selected.version_number} · ${formatDateTime(selected.computed_at) ?? ""}`
                }
              />
              <MetricCard
                label="Katkı Marjı"
                formatted={formatRatioAsPercent(selected.margin_ratio)}
                exact={selected.margin_ratio}
                support="Motorun yayınladığı oran"
              />
              <MetricCard
                label="Mevzuat Baseline"
                formatted={
                  baseline === null
                    ? null
                    : `${formatInteger(baseline.effective_rule_count) ?? "0"} / ${
                        formatInteger(baseline.rule_count) ?? "0"
                      }`
                }
                support="Yürürlükteki kural / toplam kural"
                emptyText="Baseline doğrulanamadı"
                badge={
                  baseline === null ? null : (
                    <StatusPill
                      tone={
                        baseline.status === "ready"
                          ? "ok"
                          : baseline.status === "degraded"
                            ? "warn"
                            : "fail"
                      }
                      label={
                        baseline.status === "ready"
                          ? "Doğrulandı"
                          : baseline.status === "degraded"
                            ? "Uyarı"
                            : "Hata"
                      }
                    />
                  )
                }
              />
            </>
          )}
        </section>

        <div className={styles.mainGrid}>
          <div className={styles.column}>
            <section className={styles.panel} aria-labelledby="sector-table-title">
              <div className={styles.panelHead}>
                <h2 className={styles.panelTitle} id="sector-table-title">
                  Sektörel Maliyet Girdileri
                </h2>
                <span className={styles.panelHint}>
                  {formatInteger(overview?.calculation_count ?? 0) ?? "0"} hesaplama
                </span>
              </div>
              {loading ? (
                <PanelSkeleton lines={5} />
              ) : (
                <SectorCostTable calculations={overview?.calculations ?? []} />
              )}
            </section>

          </div>

          <div className={styles.column}>
            <section className={styles.panel} aria-labelledby="distribution-title">
              <div className={styles.panelHead}>
                <h2 className={styles.panelTitle} id="distribution-title">
                  Maliyet Dağılımı
                </h2>
                <span className={styles.panelHint}>{selected?.name ?? ""}</span>
              </div>
              {loading ? (
                <ChartSkeleton />
              ) : (
                <CostDistributionChart
                  entries={selected?.cost_categories[0]?.entries ?? []}
                  groupLabel={selected?.engine_title ?? selected?.calculation_type ?? ""}
                />
              )}
            </section>
            <section className={styles.panel} aria-labelledby="trend-title">
              <div className={styles.panelHead}>
                <h2 className={styles.panelTitle} id="trend-title">
                  Sürüm Bazlı Maliyet Seyri
                </h2>
                <span className={styles.panelHint}>{selected?.name ?? ""}</span>
              </div>
              {loading ? (
                <ChartSkeleton />
              ) : (
                <CostTrendChart entries={selectedTimeline} measure="unit_cost" />
              )}
            </section>
          </div>

          <div className={`${styles.column} ${styles.railColumn}`}>
            {loading || baseline === null ? (
              <section className={styles.panel}>
                <PanelSkeleton lines={6} />
              </section>
            ) : (
              <RegulatoryReadinessCard baseline={baseline} />
            )}
            {loading || overview === null ? (
              <section className={styles.panel}>
                <PanelSkeleton lines={3} />
              </section>
            ) : (
              <>
                <DecisionAnalysisCard summary={overview.decision_analysis} />
                <WidgetPreviewCard summary={overview.widget} />
              </>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
