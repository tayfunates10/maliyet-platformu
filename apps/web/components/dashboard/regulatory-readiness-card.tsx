import type { RegulatoryBaseline, RegulatoryRule } from "@/lib/dashboard-api";
import { formatDate, formatInteger } from "@/lib/decimal-format.mjs";
import { PanelEmptyState, StatusPill, type StatusTone } from "./dashboard-states";
import styles from "./dashboard.module.css";

const BASELINE_TONE: Readonly<Record<RegulatoryBaseline["status"], StatusTone>> = Object.freeze({
  ready: "ok",
  degraded: "warn",
  unavailable: "fail",
});

const BASELINE_LABEL: Readonly<Record<RegulatoryBaseline["status"], string>> = Object.freeze({
  ready: "Doğrulandı",
  degraded: "Eksik/Uyarı",
  unavailable: "Doğrulanamadı",
});

const RULE_TONE: Readonly<Record<RegulatoryRule["state"], StatusTone>> = Object.freeze({
  effective: "ok",
  not_effective: "warn",
  ambiguous: "fail",
});

const RULE_LABEL: Readonly<Record<RegulatoryRule["state"], string>> = Object.freeze({
  effective: "Yürürlükte",
  not_effective: "Yürürlükte değil",
  ambiguous: "Belirsiz",
});

/**
 * Regulatory baseline integrity and coverage.
 *
 * This panel reports what the backend proved: that the curated sources still
 * hash to their stored digests and that each rule resolves to exactly one
 * effective version. It is not a compliance score, and it never renders a clean
 * state the backend did not report — an unverifiable baseline reads as a
 * failure, not as silence.
 */
export function RegulatoryReadinessCard({
  baseline,
}: Readonly<{ baseline: RegulatoryBaseline }>) {
  const evaluatedAt = formatDate(baseline.evaluated_at);

  if (baseline.status === "unavailable") {
    return (
      <section className={styles.panel} aria-labelledby="readiness-title">
        <div className={styles.panelHead}>
          <h2 className={styles.panelTitle} id="readiness-title">
            Mevzuat Baseline
          </h2>
          <StatusPill tone="fail" label={BASELINE_LABEL.unavailable} />
        </div>
        <PanelEmptyState
          title="Baseline doğrulanamadı"
          description="Mevzuat kural tabanı okunamadığı için hiçbir uyum durumu raporlanamaz."
        />
        {baseline.issues.length === 0 ? null : (
          <ul className={styles.issueList}>
            {baseline.issues.map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
        )}
      </section>
    );
  }

  return (
    <section className={styles.panel} aria-labelledby="readiness-title">
      <div className={styles.panelHead}>
        <h2 className={styles.panelTitle} id="readiness-title">
          Mevzuat Baseline
        </h2>
        <StatusPill tone={BASELINE_TONE[baseline.status]} label={BASELINE_LABEL[baseline.status]} />
      </div>

      <dl className={styles.definitionGrid}>
        <div>
          <dt>Veri seti</dt>
          <dd>
            {baseline.dataset ?? "—"}
            {baseline.dataset_version === null ? "" : ` v${baseline.dataset_version}`}
          </dd>
        </div>
        <div>
          <dt>Yürürlükteki kural</dt>
          <dd>
            {formatInteger(baseline.effective_rule_count) ?? "—"} /{" "}
            {formatInteger(baseline.rule_count) ?? "—"}
          </dd>
        </div>
        <div>
          <dt>Doğrulanmış kaynak</dt>
          <dd>{formatInteger(baseline.source_count) ?? "—"}</dd>
        </div>
        <div>
          <dt>Değerlendirme</dt>
          <dd>{evaluatedAt ?? "—"}</dd>
        </div>
      </dl>

      {baseline.issues.length === 0 ? null : (
        <ul className={styles.issueList} aria-label="Mevzuat baseline bulguları">
          {baseline.issues.map((issue) => (
            <li key={issue}>{issue}</li>
          ))}
        </ul>
      )}

      <ul className={styles.ruleList} style={{ marginTop: "0.85rem" }}>
        {baseline.rules.map((rule) => (
          <li key={rule.code} className={styles.ruleItem}>
            <span>
              <span className={styles.ruleCode}>{rule.code}</span>
              <br />
              <span className={styles.ruleMeta}>
                {rule.category}
                {rule.effective_from === null
                  ? ""
                  : ` · ${formatDate(rule.effective_from) ?? rule.effective_from}${
                      rule.revision === null ? "" : ` · rev ${rule.revision}`
                    }`}
              </span>
            </span>
            <StatusPill tone={RULE_TONE[rule.state]} label={RULE_LABEL[rule.state]} />
          </li>
        ))}
      </ul>

      <p className={styles.panelNote}>
        Durum, kaynak özet doğrulaması ve yürürlük tarihi çözümlemesinden gelir; bir uyum yüzdesi
        değildir. Doğrulanamayan baseline fail-closed raporlanır.
      </p>
    </section>
  );
}
