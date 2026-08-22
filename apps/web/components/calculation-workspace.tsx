"use client";

import { type FormEvent, useState } from "react";
import {
  type CalculationSummary,
  createCalculation,
  type EngineSummary,
  listCalculations,
  listWorkspaceEngines,
  listWorkspaceOrganizations,
  loginWorkspace,
  logoutWorkspace,
  type WorkspaceOrganization,
} from "@/lib/calculation-workspace-api";
import { CalculationExecutionPanel } from "./calculation-execution-panel";
import styles from "./calculation-workspace.module.css";

type Notice = Readonly<{ kind: "error" | "success" | "info"; text: string }> | null;

const WRITE_ROLES = new Set(["owner", "admin", "accountant", "analyst"]);

function friendlyError(error: unknown): string {
  if (error instanceof Error) {
    if (error.message === "authentication_required") return "Oturum doğrulanamadı.";
    if (error.message === "access_denied") return "Bu organizasyon için erişim yetkiniz yok.";
    if (error.message === "invalid_request") return "Gönderilen hesaplama bilgileri geçersiz.";
    if (error.message === "conflict") return "İşlem mevcut durumla çakıştı.";
  }
  return "İşlem tamamlanamadı. Lütfen bilgileri kontrol edip tekrar deneyin.";
}

export function CalculationWorkspace() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [organizations, setOrganizations] = useState<readonly WorkspaceOrganization[]>([]);
  const [engines, setEngines] = useState<readonly EngineSummary[]>([]);
  const [organizationId, setOrganizationId] = useState("");
  const [calculations, setCalculations] = useState<readonly CalculationSummary[]>([]);
  const [selectedCalculationId, setSelectedCalculationId] = useState("");
  const [name, setName] = useState("");
  const [engineKey, setEngineKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);

  const selectedOrganization = organizations.find((organization) => organization.id === organizationId) ?? null;
  const selectedCalculation = calculations.find((calculation) => calculation.id === selectedCalculationId) ?? null;
  const selectedCalculationEngine = selectedCalculation === null
    ? null
    : engines.find((engine) => engine.key === selectedCalculation.calculation_type) ?? null;
  const canWrite = selectedOrganization !== null && WRITE_ROLES.has(selectedOrganization.role);

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setNotice(null);
    try {
      const nextToken = await loginWorkspace(email.trim(), password);
      setPassword("");
      const [nextOrganizations, nextEngines] = await Promise.all([
        listWorkspaceOrganizations(nextToken),
        listWorkspaceEngines(nextToken),
      ]);
      setToken(nextToken);
      setOrganizations(nextOrganizations);
      setEngines(nextEngines);
      const firstOrganization = nextOrganizations[0] ?? null;
      const firstEngine = nextEngines[0] ?? null;
      setOrganizationId(firstOrganization?.id ?? "");
      setEngineKey(firstEngine?.key ?? "");
      setSelectedCalculationId("");
      if (firstOrganization !== null) {
        setCalculations(await listCalculations(nextToken, firstOrganization.id));
      } else {
        setCalculations([]);
      }
      setNotice({ kind: "success", text: "Oturum açıldı. Hesaplama çalışma alanı hazır." });
    } catch (error) {
      setToken(null);
      setOrganizations([]);
      setEngines([]);
      setCalculations([]);
      setSelectedCalculationId("");
      setPassword("");
      setNotice({ kind: "error", text: friendlyError(error) });
    } finally {
      setBusy(false);
    }
  }

  async function handleOrganizationChange(nextOrganizationId: string) {
    setOrganizationId(nextOrganizationId);
    setCalculations([]);
    setSelectedCalculationId("");
    setNotice(null);
    if (token === null || nextOrganizationId === "") return;
    setBusy(true);
    try {
      setCalculations(await listCalculations(token, nextOrganizationId));
    } catch (error) {
      setNotice({ kind: "error", text: friendlyError(error) });
    } finally {
      setBusy(false);
    }
  }

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (token === null || selectedOrganization === null || !canWrite) return;
    setBusy(true);
    setNotice(null);
    try {
      const created = await createCalculation(token, selectedOrganization.id, {
        name,
        calculation_type: engineKey,
      });
      setName("");
      setCalculations((current) => Object.freeze([created, ...current]));
      setSelectedCalculationId(created.id);
      setNotice({ kind: "success", text: "Hesaplama kaydı oluşturuldu ve yürütme panelinde açıldı." });
    } catch (error) {
      setNotice({ kind: "error", text: friendlyError(error) });
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    if (token === null) return;
    setBusy(true);
    setNotice(null);
    try {
      await logoutWorkspace(token);
      setToken(null);
      setPassword("");
      setOrganizations([]);
      setEngines([]);
      setOrganizationId("");
      setCalculations([]);
      setSelectedCalculationId("");
      setName("");
      setEngineKey("");
      setNotice({ kind: "info", text: "Sunucu oturumu kapatıldı ve yerel oturum bilgisi temizlendi." });
    } catch (error) {
      setNotice({ kind: "error", text: friendlyError(error) });
    } finally {
      setBusy(false);
    }
  }

  if (token === null) {
    return (
      <section className={styles.panel} aria-labelledby="workspace-login-title">
        <h2 id="workspace-login-title">Yönetim oturumu</h2>
        <p>Bearer oturumu yalnız bu sayfanın belleğinde tutulur; tarayıcı depolamasına yazılmaz.</p>
        <form className={styles.form} onSubmit={handleLogin}>
          <label>
            E-posta
            <input type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)} />
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
          <button type="submit" disabled={busy}>{busy ? "Bağlanıyor…" : "Oturum aç"}</button>
        </form>
        {notice !== null ? <p role={notice.kind === "error" ? "alert" : "status"}>{notice.text}</p> : null}
      </section>
    );
  }

  return (
    <section className={styles.workspace} aria-labelledby="workspace-title">
      <div className={styles.toolbar}>
        <div>
          <p className={styles.kicker}>Tenant çalışma alanı</p>
          <h2 id="workspace-title">Hesaplamalar</h2>
        </div>
        <button type="button" className={styles.secondary} onClick={() => void logout()} disabled={busy}>Oturumu kapat</button>
      </div>

      <div className={styles.grid}>
        <div className={styles.panel}>
          <h3>Organizasyon</h3>
          <label>
            Çalışma alanı
            <select value={organizationId} onChange={(event) => void handleOrganizationChange(event.target.value)} disabled={busy}>
              {organizations.length === 0 ? <option value="">Organizasyon bulunamadı</option> : null}
              {organizations.map((organization) => (
                <option key={organization.id} value={organization.id}>
                  {organization.legal_name} · {organization.role}
                </option>
              ))}
            </select>
          </label>
          {selectedOrganization !== null && !canWrite ? (
            <p role="status">Bu rol salt-okunur. Mevcut hesaplamaları ve kayıtlı sonuçları görüntüleyebilirsiniz.</p>
          ) : null}
        </div>

        <div className={styles.panel}>
          <h3>Yeni hesaplama</h3>
          <form className={styles.form} onSubmit={handleCreate}>
            <label>
              Hesaplama adı
              <input maxLength={240} required value={name} onChange={(event) => setName(event.target.value)} disabled={!canWrite || busy} />
            </label>
            <label>
              Sektör motoru
              <select required value={engineKey} onChange={(event) => setEngineKey(event.target.value)} disabled={!canWrite || busy}>
                {engines.map((engine) => (
                  <option key={engine.key} value={engine.key}>{engine.title}</option>
                ))}
              </select>
            </label>
            <button type="submit" disabled={!canWrite || busy || engineKey === ""}>{busy ? "İşleniyor…" : "Hesaplama oluştur"}</button>
          </form>
        </div>
      </div>

      {notice !== null ? <p className={styles.notice} role={notice.kind === "error" ? "alert" : "status"}>{notice.text}</p> : null}

      <div className={styles.panel}>
        <div className={styles.listHeading}>
          <h3>Mevcut hesaplamalar</h3>
          <span>{calculations.length} kayıt</span>
        </div>
        {calculations.length === 0 ? (
          <p>Bu organizasyonda henüz hesaplama yok.</p>
        ) : (
          <ul className={styles.list}>
            {calculations.map((calculation) => {
              const engine = engines.find((item) => item.key === calculation.calculation_type);
              const selected = calculation.id === selectedCalculationId;
              return (
                <li key={calculation.id}>
                  <div>
                    <strong>{calculation.name}</strong>
                    <span>{engine?.title ?? calculation.calculation_type}</span>
                  </div>
                  <div className={styles.listActions}>
                    <time dateTime={calculation.updated_at}>{new Date(calculation.updated_at).toLocaleString("tr-TR")}</time>
                    <button
                      type="button"
                      className={styles.secondary}
                      aria-pressed={selected}
                      onClick={() => setSelectedCalculationId(selected ? "" : calculation.id)}
                    >
                      {selected ? "Kapat" : "Aç / çalıştır"}
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {selectedOrganization !== null && selectedCalculation !== null && selectedCalculationEngine !== null ? (
        <CalculationExecutionPanel
          key={selectedCalculation.id}
          token={token}
          organizationId={selectedOrganization.id}
          calculation={selectedCalculation}
          engine={selectedCalculationEngine}
          canWrite={canWrite}
        />
      ) : null}
    </section>
  );
}
