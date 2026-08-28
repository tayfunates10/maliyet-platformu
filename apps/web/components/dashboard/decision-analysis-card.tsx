import Link from "next/link";
import type { DecisionAnalysisSummary } from "@/lib/dashboard-api";
import { formatDateTime, formatInteger } from "@/lib/decimal-format.mjs";
import { PanelEmptyState } from "./dashboard-states";
import styles from "./dashboard.module.css";

/**
 * Decision-analysis provenance for this tenant.
 *
 * Only stored artifacts are reported. Ratios are not replayed or recomputed
 * here; the workspace that produced them remains the place to open one, so the
 * card links there instead of restating a financial result out of context.
 */
export function DecisionAnalysisCard({
  summary,
}: Readonly<{ summary: DecisionAnalysisSummary }>) {
  return (
    <section className={styles.panel} aria-labelledby="decision-title">
      <div className={styles.panelHead}>
        <h2 className={styles.panelTitle} id="decision-title">
          Karar Analizi
        </h2>
        <span className={styles.panelHint}>
          {formatInteger(summary.artifact_count) ?? "0"} kayıt
        </span>
      </div>

      {summary.artifact_count === 0 || summary.latest_artifact_id === null ? (
        <PanelEmptyState
          title="Henüz karar senaryosu yok"
          description="Bu organizasyon için karşılaştırılabilir bir yatırım/senaryo analizi oluşturulmadı."
          action={
            <Link className={styles.ghostAction} href="/decision-analysis">
              Karar analizine git
            </Link>
          }
        />
      ) : (
        <>
          <dl className={styles.definitionGrid}>
            <div>
              <dt>Motor</dt>
              <dd>{summary.latest_engine_version ?? "—"}</dd>
            </div>
            <div>
              <dt>Son analiz</dt>
              <dd>{formatDateTime(summary.latest_created_at) ?? "—"}</dd>
            </div>
          </dl>
          <p className={styles.panelNote}>
            Output SHA-256
            <br />
            <span className={styles.digest}>{summary.latest_output_sha256 ?? "—"}</span>
          </p>
          <p className={styles.panelNote}>
            <Link className={styles.ghostAction} href="/decision-analysis">
              Analizi doğrula ve aç
            </Link>
          </p>
        </>
      )}
    </section>
  );
}
