import type { ReactNode } from "react";
import styles from "./dashboard.module.css";

/**
 * One headline figure.
 *
 * `formatted` is the localised presentation of a value the backend published;
 * `exact` is that same backend string, shown verbatim so full Decimal precision
 * stays auditable next to the rounded display form. When the engine publishes
 * no such figure, `formatted` is null and the card states that plainly instead
 * of showing a zero.
 */
export function MetricCard({
  label,
  formatted,
  exact,
  support,
  emptyText = "Bu motor bu değeri yayınlamıyor",
  badge,
}: Readonly<{
  label: string;
  formatted: string | null;
  exact?: string | null;
  support?: string;
  emptyText?: string;
  badge?: ReactNode;
}>) {
  return (
    <article className={styles.metricCard}>
      <h3 className={styles.metricLabel}>
        {label}
        {badge}
      </h3>
      {formatted === null ? (
        <p className={`${styles.metricValue} ${styles.metricValueEmpty}`}>{emptyText}</p>
      ) : (
        <p className={styles.metricValue}>{formatted}</p>
      )}
      {formatted !== null && exact ? (
        <p className={styles.metricExact} title="Motorun yayınladığı tam Decimal değer">
          {exact}
        </p>
      ) : null}
      {support === undefined ? null : <p className={styles.metricSupport}>{support}</p>}
    </article>
  );
}
