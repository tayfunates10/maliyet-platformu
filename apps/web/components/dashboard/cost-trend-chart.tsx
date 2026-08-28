import type { DashboardTimelineEntry } from "@/lib/dashboard-api";
import {
  formatCurrency,
  formatDateTime,
  geometryPosition,
  maxDecimalText,
  minDecimalText,
} from "@/lib/decimal-format.mjs";
import { PanelEmptyState } from "./dashboard-states";
import styles from "./dashboard.module.css";

const WIDTH = 560;
const HEIGHT = 210;
const PADDING = Object.freeze({ top: 18, right: 14, bottom: 30, left: 14 });
const PLOT_WIDTH = WIDTH - PADDING.left - PADDING.right;
const PLOT_HEIGHT = HEIGHT - PADDING.top - PADDING.bottom;

type Point = Readonly<{
  key: string;
  label: string;
  amount: string;
  version: number;
  x: number;
  y: number;
}>;

/**
 * One calculation's cost across its recorded versions, oldest to newest.
 *
 * Each point is an immutable engine execution of the same calculation, so the
 * series compares like with like — versions of different engines are different
 * financial objects and are never plotted together. The vertical axis is a
 * single measure over the observed value band rather than from zero, and the
 * band's endpoints are labelled so the scale is stated instead of implied.
 */
export function CostTrendChart({
  entries,
  measure,
}: Readonly<{ entries: readonly DashboardTimelineEntry[]; measure: "total_cost" | "unit_cost" }>) {
  const usable = entries.filter((entry) => entry[measure] !== null);
  const measureLabel = measure === "total_cost" ? "Toplam maliyet" : "Birim maliyet";

  if (usable.length < 2) {
    return (
      <PanelEmptyState
        title="Trend için yeterli veri yok"
        description={
          usable.length === 0
            ? `Bu hesaplamanın kayıtlı sürümleri ${measureLabel.toLocaleLowerCase("tr-TR")} yayınlamıyor.`
            : "Trend göstermek için en az iki kayıtlı sürüm gerekli."
        }
      />
    );
  }

  const amounts = usable.map((entry) => entry[measure] as string);
  const floor = minDecimalText(amounts);
  const ceiling = maxDecimalText(amounts);
  if (floor === null || ceiling === null) {
    return (
      <PanelEmptyState
        title="Trend için yeterli veri yok"
        description="Kayıtlı sürümlerde çizilebilir bir değer bulunamadı."
      />
    );
  }

  const points: Point[] = usable.map((entry, index) => {
    const amount = entry[measure] as string;
    const position = geometryPosition(amount, floor, ceiling);
    return {
      key: `${entry.calculation_id}-${entry.version_number}`,
      label: `${entry.calculation_name} · s${entry.version_number}`,
      amount,
      version: entry.version_number,
      x: PADDING.left + (index / (usable.length - 1)) * PLOT_WIDTH,
      // Leave a tenth of the plot as headroom at each end so the extreme points
      // never sit on the frame.
      y: PADDING.top + PLOT_HEIGHT * (0.9 - position * 0.8),
    };
  });

  const line = points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
    .join(" ");
  const first = points[0];
  const last = points[points.length - 1];
  const area =
    first === undefined || last === undefined
      ? ""
      : `${line} L ${last.x.toFixed(2)} ${PADDING.top + PLOT_HEIGHT} L ${first.x.toFixed(2)} ${PADDING.top + PLOT_HEIGHT} Z`;
  const description = points
    .map((point) => `${point.label}: ${formatCurrency(point.amount) ?? point.amount}`)
    .join(", ");

  return (
    <figure className={styles.chartFigure}>
      <svg
        className={styles.chartSvg}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={`${measureLabel} sürüm geçmişi. ${description}.`}
      >
        <title>{measureLabel} sürüm geçmişi</title>
        {[0.1, 0.5, 0.9].map((fraction) => (
          <line
            key={`grid-${fraction}`}
            className={styles.gridLine}
            x1={PADDING.left}
            x2={PADDING.left + PLOT_WIDTH}
            y1={PADDING.top + PLOT_HEIGHT * fraction}
            y2={PADDING.top + PLOT_HEIGHT * fraction}
          />
        ))}
        <path d={area} fill="var(--chart-1)" opacity="0.1" />
        <path d={line} fill="none" stroke="var(--chart-1)" strokeWidth="2" strokeLinejoin="round" />
        {points.map((point) => (
          <circle
            key={point.key}
            cx={point.x}
            cy={point.y}
            r="5"
            fill="var(--chart-1)"
            stroke="var(--surface)"
            strokeWidth="2"
          >
            <title>{`${point.label}: ${formatCurrency(point.amount) ?? point.amount}`}</title>
          </circle>
        ))}
        {/* The band endpoints are labelled: the axis does not start at zero. */}
        <text className={styles.axisText} x={PADDING.left} y={PADDING.top + PLOT_HEIGHT * 0.1 - 5}>
          {formatCurrency(ceiling) ?? ceiling}
        </text>
        <text className={styles.axisText} x={PADDING.left} y={PADDING.top + PLOT_HEIGHT * 0.9 + 12}>
          {formatCurrency(floor) ?? floor}
        </text>
        {points.map((point, index) =>
          index === 0 || index === points.length - 1 ? (
            <text
              key={`axis-${point.key}`}
              className={styles.axisText}
              x={point.x}
              y={HEIGHT - 12}
              textAnchor={index === 0 ? "start" : "end"}
            >
              {`s${point.version}`}
            </text>
          ) : null,
        )}
      </svg>
      <figcaption className={styles.panelHint}>
        {measureLabel} · {usable.length} kayıtlı sürüm · dikey eksen gözlenen değer aralığıdır (
        {formatCurrency(floor) ?? floor} – {formatCurrency(ceiling) ?? ceiling}) ·{" "}
        {formatDateTime(usable[0]?.computed_at) ?? ""} –{" "}
        {formatDateTime(usable[usable.length - 1]?.computed_at) ?? ""}
      </figcaption>
    </figure>
  );
}
