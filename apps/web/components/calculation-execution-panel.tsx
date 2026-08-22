"use client";

import { type FormEvent, useState } from "react";
import {
  type CalculationExecution,
  type CalculationVersion,
  executeCalculation,
  getEngineDetail,
  getLatestCalculationVersion,
} from "@/lib/calculation-execution-api";
import type { CalculationSummary, EngineSummary } from "@/lib/calculation-workspace-api";
import { buildSchemaTemplate, listRequiredFields } from "@/lib/json-schema-template";
import { CalculationResultSummary } from "./calculation-result-summary";
import { SchemaFieldEditor } from "./schema-field-editor";
import styles from "./calculation-workspace.module.css";

type Props = Readonly<{
  token: string;
  organizationId: string;
  calculation: CalculationSummary;
  engine: EngineSummary;
  canWrite: boolean;
}>;

type Notice = Readonly<{ kind: "error" | "success" | "info"; text: string }> | null;

type JsonObject = Readonly<Record<string, unknown>>;

function friendlyError(error: unknown): string {
  if (error instanceof Error) {
    if (error.message === "authentication_required") return "Oturum doğrulanamadı.";
    if (error.message === "access_denied") return "Bu işlem için yetkiniz yok.";
    if (error.message === "invalid_request") return "Motor girdisi doğrulamadan geçmedi.";
    if (error.message === "request_too_large") return "Motor girdisi izin verilen boyutu aşıyor.";
    if (error.message === "conflict") return "Motor, seçili hesaplama türüyle eşleşmiyor veya işlem çakıştı.";
  }
  return "İşlem tamamlanamadı.";
}

function pretty(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

export function CalculationExecutionPanel({ token, organizationId, calculation, engine, canWrite }: Props) {
  const [inputSchema, setInputSchema] = useState<JsonObject | null>(null);
  const [inputValue, setInputValue] = useState<JsonObject | null>(null);
  const [requiredFields, setRequiredFields] = useState<readonly string[]>([]);
  const [execution, setExecution] = useState<CalculationExecution | null>(null);
  const [latestVersion, setLatestVersion] = useState<CalculationVersion | null>(null);
  const [schemaLoaded, setSchemaLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);

  async function loadSchema() {
    setBusy(true);
    setNotice(null);
    try {
      const detail = await getEngineDetail(token, engine.key);
      if (detail.engine_version !== engine.engine_version) throw new Error("engine_version_mismatch");
      const template = buildSchemaTemplate(detail.input_schema);
      setInputSchema(detail.input_schema);
      setInputValue(template);
      setRequiredFields(listRequiredFields(detail.input_schema));
      setSchemaLoaded(true);
      setNotice({ kind: "info", text: "Motor şeması yüklendi. Decimal alanları sayı değil metin olarak tutulur ve backend doğrulamasına gönderilir." });
    } catch (error) {
      setInputSchema(null);
      setInputValue(null);
      setSchemaLoaded(false);
      setNotice({ kind: "error", text: friendlyError(error) });
    } finally {
      setBusy(false);
    }
  }

  async function loadLatestVersion() {
    setBusy(true);
    setNotice(null);
    try {
      const version = await getLatestCalculationVersion(token, organizationId, calculation.id);
      setLatestVersion(version);
      setNotice({ kind: "info", text: version === null ? "Bu hesaplama için henüz kayıtlı sürüm yok." : `Kayıtlı sürüm #${version.version} yüklendi.` });
    } catch (error) {
      setNotice({ kind: "error", text: friendlyError(error) });
    } finally {
      setBusy(false);
    }
  }

  async function handleExecute(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canWrite || !schemaLoaded || inputValue === null) return;
    setBusy(true);
    setNotice(null);
    try {
      const result = await executeCalculation(
        token,
        organizationId,
        calculation.id,
        engine.key,
        inputValue,
      );
      setExecution(result);
      setLatestVersion(null);
      setNotice({ kind: "success", text: `Hesaplama tamamlandı ve immutable sürüm #${result.version} kaydedildi.` });
    } catch (error) {
      setNotice({ kind: "error", text: friendlyError(error) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.panel}>
      <div className={styles.listHeading}>
        <div>
          <h3>Hesaplamayı çalıştır</h3>
          <p className={styles.kicker}>{engine.title} · {engine.engine_version}</p>
        </div>
        <button type="button" className={styles.secondary} onClick={() => void loadLatestVersion()} disabled={busy}>
          Son kayıtlı sonucu göster
        </button>
      </div>

      <p><strong>{calculation.name}</strong> için input şeması backend allowlist’inden alınır; tarayıcı finansal formül çalıştırmaz.</p>
      {!schemaLoaded || inputSchema === null || inputValue === null ? (
        <button type="button" className={styles.secondary} onClick={() => void loadSchema()} disabled={busy || !canWrite}>
          {busy ? "Yükleniyor…" : "Motor formunu hazırla"}
        </button>
      ) : (
        <form className={styles.form} onSubmit={handleExecute}>
          {requiredFields.length > 0 ? <p className={styles.kicker}>Zorunlu üst alanlar: {requiredFields.join(", ")}</p> : null}
          <SchemaFieldEditor
            schema={inputSchema}
            value={inputValue}
            disabled={!canWrite || busy}
            onChange={setInputValue}
          />
          <details className={styles.jsonPreview}>
            <summary>Gönderilecek JSON önizlemesi</summary>
            <pre>{pretty(inputValue)}</pre>
          </details>
          <button type="submit" disabled={!canWrite || busy}>
            {busy ? "Çalıştırılıyor…" : "Hesapla ve sürüm kaydet"}
          </button>
        </form>
      )}

      {!canWrite ? <p role="status">Bu rol salt-okunur; yeni execution oluşturamaz.</p> : null}
      {notice !== null ? <p className={styles.notice} role={notice.kind === "error" ? "alert" : "status"}>{notice.text}</p> : null}

      {execution !== null ? (
        <div className={styles.result}>
          <h4>Yeni sürüm #{execution.version}</h4>
          <CalculationResultSummary snapshot={execution.output_snapshot} />
          <p>Output SHA-256: <code>{execution.output_sha256}</code></p>
          <details className={styles.jsonPreview}>
            <summary>Tam output snapshot</summary>
            <pre>{pretty(execution.output_snapshot)}</pre>
          </details>
        </div>
      ) : null}

      {latestVersion !== null ? (
        <div className={styles.result}>
          <h4>Kayıtlı sürüm #{latestVersion.version}</h4>
          <p>Engine: {latestVersion.engine_key ?? "legacy"} · {latestVersion.engine_version}</p>
          <CalculationResultSummary snapshot={latestVersion.output_snapshot} />
          {latestVersion.output_sha256 !== null ? <p>Output SHA-256: <code>{latestVersion.output_sha256}</code></p> : null}
          <details className={styles.jsonPreview}>
            <summary>Tam output snapshot</summary>
            <pre>{pretty(latestVersion.output_snapshot)}</pre>
          </details>
        </div>
      ) : null}
    </div>
  );
}
