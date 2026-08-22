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
import styles from "./calculation-workspace.module.css";

type Props = Readonly<{
  token: string;
  organizationId: string;
  calculation: CalculationSummary;
  engine: EngineSummary;
  canWrite: boolean;
}>;

type Notice = Readonly<{ kind: "error" | "success" | "info"; text: string }> | null;

function friendlyError(error: unknown): string {
  if (error instanceof SyntaxError) return "Girdi geçerli JSON olmalıdır.";
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
  const [inputText, setInputText] = useState("");
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
      setInputText(pretty(template));
      setRequiredFields(listRequiredFields(detail.input_schema));
      setSchemaLoaded(true);
      setNotice({ kind: "info", text: "Motor şeması yüklendi. Decimal alanları JSON sayı değil metin olarak girilmelidir." });
    } catch (error) {
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
    if (!canWrite || !schemaLoaded) return;
    setBusy(true);
    setNotice(null);
    try {
      const parsed: unknown = JSON.parse(inputText);
      if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) throw new SyntaxError("object required");
      const result = await executeCalculation(
        token,
        organizationId,
        calculation.id,
        engine.key,
        parsed as Readonly<Record<string, unknown>>,
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
      {!schemaLoaded ? (
        <button type="button" className={styles.secondary} onClick={() => void loadSchema()} disabled={busy || !canWrite}>
          {busy ? "Yükleniyor…" : "Motor formunu hazırla"}
        </button>
      ) : (
        <form className={styles.form} onSubmit={handleExecute}>
          {requiredFields.length > 0 ? <p className={styles.kicker}>Zorunlu üst alanlar: {requiredFields.join(", ")}</p> : null}
          <label>
            Motor girdisi (JSON)
            <textarea
              rows={18}
              spellCheck={false}
              value={inputText}
              onChange={(event) => setInputText(event.target.value)}
              disabled={!canWrite || busy}
            />
          </label>
          <button type="submit" disabled={!canWrite || busy || inputText.trim() === ""}>
            {busy ? "Çalıştırılıyor…" : "Hesapla ve sürüm kaydet"}
          </button>
        </form>
      )}

      {!canWrite ? <p role="status">Bu rol salt-okunur; yeni execution oluşturamaz.</p> : null}
      {notice !== null ? <p className={styles.notice} role={notice.kind === "error" ? "alert" : "status"}>{notice.text}</p> : null}

      {execution !== null ? (
        <div className={styles.result}>
          <h4>Yeni sürüm #{execution.version}</h4>
          <p>Output SHA-256: <code>{execution.output_sha256}</code></p>
          <pre>{pretty(execution.output_snapshot)}</pre>
        </div>
      ) : null}

      {latestVersion !== null ? (
        <div className={styles.result}>
          <h4>Kayıtlı sürüm #{latestVersion.version}</h4>
          <p>Engine: {latestVersion.engine_key ?? "legacy"} · {latestVersion.engine_version}</p>
          {latestVersion.output_sha256 !== null ? <p>Output SHA-256: <code>{latestVersion.output_sha256}</code></p> : null}
          <pre>{pretty(latestVersion.output_snapshot)}</pre>
        </div>
      ) : null}
    </div>
  );
}
