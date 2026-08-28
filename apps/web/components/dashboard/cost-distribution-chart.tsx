import { formatCurrency, geometryShare, geometryTotal } from "@/lib/decimal-format.mjs";
import { turkishCategoryLabel } from "@/lib/schema-field-labels.mjs";
import { PanelEmptyState } from "./dashboard-states";
import styles from "./dashboard.module.css";

/** Fixed categorical order. Slots are assigned in sequence and never cycled. */
const SERIES_COLORS = Object.freeze([
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
  "var(--chart-6)",
]);

const SIZE = 220;
const RADIUS = 88;
const STROKE = 26;
const CENTER = SIZE / 2;
/** 2px surface gap between adjacent fills, expressed as an arc angle. */
const GAP_DEGREES = (2 / (2 * Math.PI * RADIUS)) * 360;

type Slice = Readonly<{
  key: string;
  label: string;
  amount: string;
  share: number;
  color: string;
}>;

function humanize(key: string): string {
  return turkishCategoryLabel(key) ?? key.replaceAll("_", " ");
}

function polar(angleDegrees: number, radius: number): readonly [number, number] {
  const radians = ((angleDegrees - 90) * Math.PI) / 180;
  return [CENTER + radius * Math.cos(radians), CENTER + radius * Math.sin(radians)];
}

function arcPath(startDegrees: number, endDegrees: number): string {
  const sweep = endDegrees - startDegrees;
  // A full circle cannot be drawn as a single arc; close it as two halves.
  if (sweep >= 359.9) {
    const [ax, ay] = polar(0, RADIUS);
    const [bx, by] = polar(180, RADIUS);
    return `M ${ax} ${ay} A ${RADIUS} ${RADIUS} 0 1 1 ${bx} ${by} A ${RADIUS} ${RADIUS} 0 1 1 ${ax} ${ay}`;
  }
  const [startX, startY] = polar(startDegrees, RADIUS);
  const [endX, endY] = polar(endDegrees, RADIUS);
  const largeArc = sweep > 180 ? 1 : 0;
  return `M ${startX} ${startY} A ${RADIUS} ${RADIUS} 0 ${largeArc} 1 ${endX} ${endY}`;
}

/**
 * Cost distribution of one engine-published breakdown.
 *
 * Arc geometry uses exact scaled-integer shares, and every figure shown to the
 * user is the backend's own Decimal string formatted for display. The centre
 * total is a layout aggregate of that single breakdown and is labelled as such;
 * it is never combined across engines.
 */
export function CostDistributionChart({
  entries,
  groupLabel,
}: Readonly<{ entries: ReadonlyArray<readonly [string, string]>; groupLabel: string }>) {
  if (entries.length === 0) {
    return (
      <PanelEmptyState
        title="Maliyet dağılımı yok"
        description="Seçili hesaplama sürümü kategori bazlı maliyet dağılımı yayınlamıyor."
      />
    );
  }

  const total = geometryTotal(entries.map(([, amount]) => amount));
  if (total === null) {
    return (
      <PanelEmptyState
        title="Maliyet dağılımı yok"
        description="Seçili hesaplama sürümü kategori bazlı maliyet dağılımı yayınlamıyor."
      />
    );
  }

  const ranked = [...entries].sort(
    (left, right) => geometryShare(right[1], total) - geometryShare(left[1], total),
  );
  const slices: Slice[] = ranked.map(([key, amount], index) => ({
    key,
    label: humanize(key),
    amount,
    share: geometryShare(amount, total),
    color: SERIES_COLORS[index % SERIES_COLORS.length] ?? "var(--chart-6)",
  }));

  const formattedTotal = formatCurrency(total);
  let cursor = 0;
  const description = slices
    .map((slice) => `${slice.label}: ${formatCurrency(slice.amount) ?? slice.amount}`)
    .join(", ");

  return (
    <figure className={styles.chartFigure}>
      <svg
        className={styles.chartSvg}
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        role="img"
        aria-label={`${groupLabel} kategori dağılımı. ${description}.`}
        style={{ maxWidth: `${SIZE}px`, margin: "0 auto" }}
      >
        {slices.map((slice) => {
          const sweep = slice.share * 360;
          const start = cursor;
          cursor += sweep;
          if (sweep <= 0) return null;
          const gap = sweep > GAP_DEGREES * 2 ? GAP_DEGREES : 0;
          return (
            <path
              key={slice.key}
              d={arcPath(start, start + sweep - gap)}
              fill="none"
              stroke={slice.color}
              strokeWidth={STROKE}
              strokeLinecap="butt"
            />
          );
        })}
        <text x={CENTER} y={CENTER - 6} textAnchor="middle" className={styles.donutCenterLabel}>
          Dağılım toplamı
        </text>
        <text x={CENTER} y={CENTER + 12} textAnchor="middle" className={styles.donutCenterValue}>
          {formattedTotal ?? "—"}
        </text>
      </svg>
      <figcaption className={styles.panelHint}>
        {groupLabel} · yalnız bu hesaplama sürümünün kendi dağılımıdır
      </figcaption>
      <ul className={styles.legend}>
        {slices.map((slice) => (
          <li key={slice.key} className={styles.legendItem}>
            <span
              className={styles.legendSwatch}
              style={{ background: slice.color }}
              aria-hidden="true"
            />
            <span className={styles.legendLabel} title={slice.label}>
              {slice.label}
            </span>
            <span className={styles.legendValue}>
              {formatCurrency(slice.amount) ?? slice.amount}
            </span>
          </li>
        ))}
      </ul>
    </figure>
  );
}
