"use client";

import { type FormEvent, useState } from "react";
import {
  listWorkspaceOrganizations,
  loginWorkspace,
  logoutWorkspace,
  type WorkspaceOrganization,
  WorkspaceApiError,
} from "@/lib/calculation-workspace-api";
import {
  type DecisionAnalysisInput,
  type DecisionAnalysisResult,
  runDecisionAnalysis,
  type ScenarioKey,
} from "@/lib/decision-analysis-api";
import styles from "./calculation-workspace.module.css";

type Notice = Readonly<{ kind: "error" | "success" | "info"; text: string }> | null;

type ScenarioDraft = Readonly<{ key: ScenarioKey; revenue: string; costs: string }>;

const INITIAL_SCENARIOS: readonly ScenarioDraft[] = Object.freeze([
  Object.freeze({ key: "pessimistic", revenue: "", costs: "" }),
  Object.freeze({ key: "normal", revenue: "", costs: "" }),
  Object.freeze({ key: "optimistic", revenue: "", costs: "" }),
]);

function friendlyError(error: unknown): string {
  if (error instanceof WorkspaceApiError) {
    if (error.code === "authentication_required") return "Oturum doğrulanamadı.";
    if (error.code === "access_denied") return "Bu organizasyon için erişim yetkiniz yok.";
    if (error.code === "invalid_request") return "Yatırım veya senaryo girdileri geçersiz.";
    if (error.code === "rate_limited") return "İstek sınırına ulaşıldı. Daha sonra tekrar deneyin.";
  }
  return "Karar analizi tamamlanamadı. Girdileri kontrol edip tekrar deneyin.";
}

function exactRatio(ratio: string | null): string {
  return ratio ?? "—";
}

export function DecisionAnalysisWorkspace() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [organizations, setOrganizations] = useState<readonly WorkspaceOrganization[]>([]);
  const [organizationId, setOrganizationId] = useState("");
  const [initialInvestment, setInitialInvestment] = useState("");
  const [netReturn, setNetReturn] = useState("");
  const [equity, setEquity] = useState("");
  const [netIncome, setNetIncome] = useState("");
  const [investedCapital, setInvestedCapital] = useState("");
  const [nopat, setNopat] = useState("");
  const [scenarios, setScenarios] = useState<readonly ScenarioDraft[]>(INITIAL_SCENARIOS);
  const [result, setResult] = useState<DecisionAnalysisResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setNotice(null);
    try {
      const nextToken = await loginWorkspace(email.trim(), password);
      setPassword("");
      const nextOrganizations = await listWorkspaceOrganizations(nextToken);
      setToken(nextToken);
      setOrganizations(nextOrganizations);
      setOrganizationId(nextOrganizations[0]?.id ?? "");
      setNotice({ kind: "success", text: "Oturum açıldı. Karar analizi çalışma alanı hazır." });
    } catch (error) {
      setToken(null);
      setOrganizations([]);
      setOrganizationId("");
      setPassword("");
      setNotice({ kind: "error", text: friendlyError(error) });
    } finally {
      setBusy(false);
    }
  }

  function updateScenario(key: ScenarioKey, field: "revenue" | "costs", value: string) {
    setScenarios((current) =>
      Object.freeze(
        current.map((scenario) =>
          scenario.key === key ? Object.freeze({ ...scenario, [field]: value }) : scenario,
        ),
      ),
    );
    setResult(null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (token === null || organizationId === "") return;
    const input: DecisionAnalysisInput = Object.freeze({
      initial_investment: initialInvestment,
      net_return: netReturn,
      equity,
      net_income: netIncome,
      invested_capital: investedCapital,
      net_operating_profit_after_tax: nopat,
      scenarios,
    });
    setBusy(true);
    setNotice(null);
    setResult(null);
    try {
      setResult(await runDecisionAnalysis(token, organizationId, input));
      setNotice({ kind: "success", text: "Karar analizi hesaplandı." });
    } catch (error) {
      setNotice({ kind: "error", text: friendlyError(error) });
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    if (token === null) return;
    setBusy(true);
    try {
      await logoutWorkspace(token);
      setToken(null);
      setOrganizations([]);
      setOrganizationId("");
      setResult(null);
      setPassword("");
      setNotice({ kind: "info", text: "Sunucu oturumu kapatıldı ve yerel oturum bilgisi temizlendi." });
    } catch (error) {
      setNotice({ kind: "error", text: friendlyError(error) });
    } finally {
      setBusy(false);
    }
  }

  if (token === null) {
    return (
      <section className={styles.panel} aria-labelledby="decision-login-title">
        <h2 id="decision-login-title">Yönetim oturumu</h2>
        <p>Bearer token yalnız component belleğinde tutulur; kalıcı tarayıcı depolamasına yazılmaz.</p>
        <form className={styles.form} onSubmit={handleLogin}>
          <label>
            E-posta
            <input type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)} />
          </label>
          <label>
            Parola
            <input type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} />
          </label>
          <button type="submit" disabled={busy}>{busy ? "Bağlanıyor…" : "Oturum aç"}</button>
        </form>
        {notice !== null ? <p role={notice.kind === "error" ? "alert" : "status"}>{notice.text}</p> : null}
      </section>
    );
  }

  return (
    <section className={styles.workspace} aria-labelledby="decision-workspace-title">
      <div className={styles.toolbar}>
        <div>
          <p className={styles.kicker}>Tenant karar desteği</p>
          <h2 id="decision-workspace-title">Yatırım ve senaryo analizi</h2>
        </div>
        <button type="button" className={styles.secondary} onClick={() => void logout()} disabled={busy}>Oturumu kapat</button>
      </div>

      <form className={styles.form} onSubmit={handleSubmit}>
        <label>
          Organizasyon
          <select value={organizationId} onChange={(event) => { setOrganizationId(event.target.value); setResult(null); }} disabled={busy}>
            {organizations.length === 0 ? <option value="">Organizasyon bulunamadı</option> : null}
            {organizations.map((organization) => (
              <option key={organization.id} value={organization.id}>{organization.legal_name} · {organization.role}</option>
            ))}
          </select>
        </label>

        <div className={styles.grid}>
          <label>İlk yatırım<input inputMode="decimal" required value={initialInvestment} onChange={(event) => setInitialInvestment(event.target.value)} /></label>
          <label>Net getiri<input inputMode="decimal" required value={netReturn} onChange={(event) => setNetReturn(event.target.value)} /></label>
          <label>Özkaynak<input inputMode="decimal" required value={equity} onChange={(event) => setEquity(event.target.value)} /></label>
          <label>Net kâr<input inputMode="decimal" required value={netIncome} onChange={(event) => setNetIncome(event.target.value)} /></label>
          <label>Yatırılan sermaye<input inputMode="decimal" required value={investedCapital} onChange={(event) => setInvestedCapital(event.target.value)} /></label>
          <label>NOPAT<input inputMode="decimal" required value={nopat} onChange={(event) => setNopat(event.target.value)} /></label>
        </div>

        {scenarios.map((scenario) => (
          <fieldset key={scenario.key} className={styles.panel}>
            <legend>{scenario.key === "pessimistic" ? "Kötümser" : scenario.key === "normal" ? "Normal" : "İyimser"}</legend>
            <div className={styles.grid}>
              <label>Gelir<input inputMode="decimal" required value={scenario.revenue} onChange={(event) => updateScenario(scenario.key, "revenue", event.target.value)} /></label>
              <label>Maliyet<input inputMode="decimal" required value={scenario.costs} onChange={(event) => updateScenario(scenario.key, "costs", event.target.value)} /></label>
            </div>
          </fieldset>
        ))}

        <button type="submit" disabled={busy || organizationId === ""}>{busy ? "Hesaplanıyor…" : "Analizi hesapla"}</button>
      </form>

      {notice !== null ? <p className={styles.notice} role={notice.kind === "error" ? "alert" : "status"}>{notice.text}</p> : null}

      {result !== null ? (
        <div className={styles.panel} aria-live="polite">
          <h3>Sonuç</h3>
          <p>Motor: {result.engine_version}</p>
          <p>Oranlar backend tarafından üretilen exact Decimal metinleridir; tarayıcıda yeniden hesaplanmaz.</p>
          <ul className={styles.list}>
            <li><strong>ROI oranı</strong><span>{exactRatio(result.roi_ratio)}</span></li>
            <li><strong>ROE oranı</strong><span>{exactRatio(result.roe_ratio)}</span></li>
            <li><strong>ROIC oranı</strong><span>{exactRatio(result.roic_ratio)}</span></li>
            {result.scenarios.map((scenario) => (
              <li key={scenario.key}>
                <div><strong>{scenario.key}</strong><span>Kâr: {scenario.profit}</span></div>
                <span>Marj oranı: {exactRatio(scenario.profit_margin_ratio)}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
