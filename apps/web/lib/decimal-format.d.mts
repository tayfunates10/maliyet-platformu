export const NO_VALUE: string;
export function formatCurrency(value: unknown, locale?: string, currency?: string): string | null;
export function formatRatioAsPercent(value: unknown, locale?: string): string | null;
export function formatQuantity(
  value: unknown,
  locale?: string,
  maximumFractionDigits?: number,
): string | null;
export function formatInteger(value: unknown, locale?: string): string | null;
export function formatDateTime(value: unknown, locale?: string): string | null;
export function formatDate(value: unknown, locale?: string): string | null;
export function geometryShare(value: unknown, total: unknown): number;
export function geometryTotal(values: readonly unknown[]): string | null;
export function maxDecimalText(values: readonly unknown[]): string | null;
export function minDecimalText(values: readonly unknown[]): string | null;
export function geometryPosition(value: unknown, floor: unknown, ceiling: unknown): number;
