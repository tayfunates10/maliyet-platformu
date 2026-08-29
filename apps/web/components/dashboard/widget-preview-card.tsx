import Link from "next/link";
import type { WidgetSummary } from "@/lib/dashboard-api";
import { formatInteger } from "@/lib/decimal-format.mjs";
import { PanelEmptyState, StatusPill } from "./dashboard-states";
import styles from "./dashboard.module.css";

/**
 * Widget distribution state.
 *
 * No embed identifier is ever synthesised here. A deployment ID is a real
 * tenant credential surface, so the card reports counts and links to the
 * management screen that owns the real values rather than printing a plausible
 * looking snippet.
 */
export function WidgetPreviewCard({ summary }: Readonly<{ summary: WidgetSummary }>) {
  const published = summary.published_presentation_count > 0;

  return (
    <section className={styles.panel} aria-labelledby="widget-title">
      <div className={styles.panelHead}>
        <h2 className={styles.panelTitle} id="widget-title">
          Widget Dağıtımı
        </h2>
        {summary.deployment_count === 0 ? (
          <StatusPill tone="unknown" label="Dağıtım yok" />
        ) : (
          <StatusPill
            tone={published ? "ok" : "warn"}
            label={published ? "Yayında" : "Yayınlanmadı"}
          />
        )}
      </div>

      {summary.deployment_count === 0 ? (
        <PanelEmptyState
          title="Henüz yayınlanmış widget yok"
          description="Bu organizasyonda tanımlı widget deployment'ı bulunmuyor."
          action={
            <Link className={styles.ghostAction} href="/widget-branding">
              Widget markalamaya git
            </Link>
          }
        />
      ) : (
        <>
          <dl className={styles.definitionGrid}>
            <div>
              <dt>Deployment</dt>
              <dd>
                {formatInteger(summary.active_deployment_count) ?? "0"} /{" "}
                {formatInteger(summary.deployment_count) ?? "0"} aktif
              </dd>
            </div>
            <div>
              <dt>Yayınlanmış sunum</dt>
              <dd>{formatInteger(summary.published_presentation_count) ?? "0"}</dd>
            </div>
            <div>
              <dt>Marka profili</dt>
              <dd>{formatInteger(summary.branding_profile_count) ?? "0"}</dd>
            </div>
          </dl>
          <p className={styles.panelNote}>
            Embed kimlikleri yalnız widget markalama ekranında gösterilir; gösterge paneli örnek
            kimlik üretmez.
          </p>
          <p className={styles.panelNote}>
            <Link className={styles.ghostAction} href="/widget-branding">
              Widget markalamayı aç
            </Link>
          </p>
        </>
      )}
    </section>
  );
}
