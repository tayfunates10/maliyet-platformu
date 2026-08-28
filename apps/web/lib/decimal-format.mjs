/**
 * Locale-aware presentation of authoritative Decimal strings.
 *
 * Every helper takes the exact text the backend sent and hands it straight to
 * `Intl.NumberFormat`, which formats decimal strings without routing them
 * through a JavaScript number. `Number(value)` is deliberately never called:
 * an engine result such as "59.17729627118644067796610169" would lose digits,
 * and a percent style is used instead of multiplying a ratio by 100 by hand, so
 * no arithmetic on a financial value ever happens in the browser.
 */

const DECIMAL_PATTERN = /^-?\d+(?:\.\d+)?$/;
const DEFAULT_LOCALE = "tr-TR";
const DEFAULT_CURRENCY = "TRY";

/** Placeholder for a figure the backend genuinely does not publish. */
export const NO_VALUE = "—";

function isDecimalText(value) {
  return typeof value === "string" && value.length > 0 && DECIMAL_PATTERN.test(value);
}

export function formatCurrency(value, locale = DEFAULT_LOCALE, currency = DEFAULT_CURRENCY) {
  if (!isDecimalText(value)) return null;
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(value);
}

/**
 * Format a ratio as a percentage. `style: "percent"` performs the scaling
 * inside Intl's own decimal handling rather than in floating-point arithmetic.
 */
export function formatRatioAsPercent(value, locale = DEFAULT_LOCALE) {
  if (!isDecimalText(value)) return null;
  return new Intl.NumberFormat(locale, {
    style: "percent",
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatQuantity(value, locale = DEFAULT_LOCALE, maximumFractionDigits = 4) {
  if (!isDecimalText(value)) return null;
  return new Intl.NumberFormat(locale, { maximumFractionDigits }).format(value);
}

export function formatInteger(value, locale = DEFAULT_LOCALE) {
  if (typeof value !== "number" || !Number.isSafeInteger(value)) return null;
  return new Intl.NumberFormat(locale).format(value);
}

export function formatDateTime(value, locale = DEFAULT_LOCALE) {
  if (typeof value !== "string" || value.length === 0) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}

export function formatDate(value, locale = DEFAULT_LOCALE) {
  if (typeof value !== "string" || value.length === 0) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(parsed);
}

/**
 * Share of one Decimal string within a total, for chart geometry only.
 *
 * The result is a layout ratio, never a reported financial figure: callers use
 * it to size an arc or a bar, and always display the backend's own text next to
 * it. Values are compared as scaled BigInts so no float enters the geometry.
 */
export function geometryShare(value, total) {
  if (!isDecimalText(value) || !isDecimalText(total)) return 0;
  const scaledValue = scaleToBigInt(value);
  const scaledTotal = scaleToBigInt(total);
  if (scaledTotal === 0n) return 0;
  const permille = (scaledValue * 100000n) / scaledTotal;
  const share = Number(permille) / 100000;
  if (!Number.isFinite(share) || share < 0) return 0;
  return share > 1 ? 1 : share;
}

const GEOMETRY_SCALE = 12;

function scaleToBigInt(value) {
  const negative = value.startsWith("-");
  const unsigned = negative ? value.slice(1) : value;
  const [whole, fraction = ""] = unsigned.split(".");
  const padded = (fraction + "0".repeat(GEOMETRY_SCALE)).slice(0, GEOMETRY_SCALE);
  const magnitude = BigInt(whole + padded);
  return negative ? -magnitude : magnitude;
}

/**
 * Sum Decimal strings for chart geometry only, as exact scaled integers.
 *
 * This is never a reported total. It exists so a donut can be laid out from a
 * breakdown the backend published; the figures shown to the user remain the
 * backend's own strings.
 */
export function geometryTotal(values) {
  if (!Array.isArray(values)) return null;
  let total = 0n;
  let counted = 0;
  for (const value of values) {
    if (!isDecimalText(value)) continue;
    total += scaleToBigInt(value);
    counted += 1;
  }
  if (counted === 0) return null;
  const negative = total < 0n;
  const digits = (negative ? -total : total).toString().padStart(GEOMETRY_SCALE + 1, "0");
  const whole = digits.slice(0, digits.length - GEOMETRY_SCALE);
  const fraction = digits.slice(digits.length - GEOMETRY_SCALE).replace(/0+$/, "");
  const text = fraction.length > 0 ? `${whole}.${fraction}` : whole;
  return negative ? `-${text}` : text;
}

/**
 * Largest of a list of Decimal strings, compared as exact scaled integers.
 *
 * Used only to pick a chart's scale ceiling; the returned text is one of the
 * inputs, never a newly derived figure.
 */
export function maxDecimalText(values) {
  if (!Array.isArray(values)) return null;
  let best = null;
  let bestScaled = null;
  for (const value of values) {
    if (!isDecimalText(value)) continue;
    const scaled = scaleToBigInt(value);
    if (bestScaled === null || scaled > bestScaled) {
      best = value;
      bestScaled = scaled;
    }
  }
  return best;
}

/** Smallest of a list of Decimal strings, compared as exact scaled integers. */
export function minDecimalText(values) {
  if (!Array.isArray(values)) return null;
  let best = null;
  let bestScaled = null;
  for (const value of values) {
    if (!isDecimalText(value)) continue;
    const scaled = scaleToBigInt(value);
    if (bestScaled === null || scaled < bestScaled) {
      best = value;
      bestScaled = scaled;
    }
  }
  return best;
}

/**
 * Position of a value inside an explicit [floor, ceiling] band, for chart
 * geometry only. Returns 0.5 for a degenerate band so a flat series draws on
 * the mid-line instead of collapsing onto an axis.
 */
export function geometryPosition(value, floor, ceiling) {
  if (!isDecimalText(value) || !isDecimalText(floor) || !isDecimalText(ceiling)) return 0;
  const scaledValue = scaleToBigInt(value);
  const scaledFloor = scaleToBigInt(floor);
  const scaledCeiling = scaleToBigInt(ceiling);
  const span = scaledCeiling - scaledFloor;
  if (span <= 0n) return 0.5;
  const offset = ((scaledValue - scaledFloor) * 100000n) / span;
  const position = Number(offset) / 100000;
  if (!Number.isFinite(position)) return 0;
  return position < 0 ? 0 : position > 1 ? 1 : position;
}
