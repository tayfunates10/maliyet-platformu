import type { ReactNode } from "react";
import styles from "./dashboard.module.css";

export type StatusTone = "ok" | "warn" | "fail" | "unknown";

const TONE_CLASS: Readonly<Record<StatusTone, string>> = Object.freeze({
  ok: styles.statusOk,
  warn: styles.statusWarn,
  fail: styles.statusFail,
  unknown: styles.statusUnknown,
});

/**
 * Status is never carried by colour alone: every pill also renders a glyph and
 * a written label, so the state survives greyscale, forced colours and screen
 * readers.
 */
const TONE_GLYPH: Readonly<Record<StatusTone, string>> = Object.freeze({
  ok: "✓",
  warn: "!",
  fail: "✕",
  unknown: "?",
});

export function StatusPill({
  tone,
  label,
}: Readonly<{ tone: StatusTone; label: string }>) {
  return (
    <span className={`${styles.statusPill} ${TONE_CLASS[tone]}`}>
      <span className={styles.statusGlyph} aria-hidden="true">
        {TONE_GLYPH[tone]}
      </span>
      {label}
    </span>
  );
}

export function PanelEmptyState({
  title,
  description,
  action,
}: Readonly<{ title: string; description: string; action?: ReactNode }>) {
  return (
    <div className={styles.stateBlock}>
      <span className={styles.stateTitle}>{title}</span>
      <p style={{ margin: 0 }}>{description}</p>
      {action}
    </div>
  );
}

export function PanelErrorState({
  description,
  onRetry,
  busy = false,
}: Readonly<{ description: string; onRetry?: () => void; busy?: boolean }>) {
  return (
    <div className={`${styles.stateBlock} ${styles.stateError}`} role="alert">
      <span className={styles.stateTitle}>Veriler yüklenemedi</span>
      <p style={{ margin: 0 }}>{description}</p>
      {onRetry === undefined ? null : (
        <button type="button" className={styles.retryButton} onClick={onRetry} disabled={busy}>
          {busy ? "Yeniden deneniyor…" : "Tekrar dene"}
        </button>
      )}
    </div>
  );
}

export function PanelSkeleton({ lines = 3 }: Readonly<{ lines?: number }>) {
  // Widths double as stable identities: the placeholder rows never reorder.
  const widths = Array.from({ length: lines }, (_, index) => 100 - index * 12);
  return (
    <div className={styles.skeletonStack} aria-hidden="true">
      {widths.map((width) => (
        <div key={`skeleton-${width}`} className={styles.skeletonLine} style={{ width: `${width}%` }} />
      ))}
    </div>
  );
}

export function ChartSkeleton() {
  return <div className={styles.skeletonBlock} aria-hidden="true" />;
}
