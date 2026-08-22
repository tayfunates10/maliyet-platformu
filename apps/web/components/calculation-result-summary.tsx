import styles from "./calculation-workspace.module.css";

type Props = Readonly<{
  snapshot: Readonly<Record<string, unknown>>;
}>;

function displayValue(value: unknown): string | null {
  if (typeof value === "string") return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "boolean") return value ? "Evet" : "Hayır";
  if (value === null) return "—";
  return null;
}

function humanize(key: string): string {
  return key.replaceAll("_", " ");
}

export function CalculationResultSummary({ snapshot }: Props) {
  const entries = Object.entries(snapshot)
    .map(([key, value]) => [key, displayValue(value)] as const)
    .filter((entry): entry is readonly [string, string] => entry[1] !== null)
    .slice(0, 16);

  if (entries.length === 0) return <p>Özetlenebilir üst seviye sonuç alanı yok; ayrıntılı snapshot aşağıdadır.</p>;

  return (
    <dl className={styles.resultSummary}>
      {entries.map(([key, value]) => (
        <div key={key}>
          <dt>{humanize(key)}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}
