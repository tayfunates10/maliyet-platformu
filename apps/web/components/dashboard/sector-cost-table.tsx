import type { DashboardCalculation } from "@/lib/dashboard-api";
import { formatCurrency, NO_VALUE } from "@/lib/decimal-format.mjs";
import { turkishCategoryLabel } from "@/lib/schema-field-labels.mjs";
import { PanelEmptyState } from "./dashboard-states";
import styles from "./dashboard.module.css";

/**
 * Cost items by sector engine.
 *
 * Columns are the tenant's own calculations, one per sector engine that has a
 * recorded version; rows are the cost categories those engines published. A
 * cell is filled only where that engine published that category, and shows an
 * explicit dash otherwise — an absent category is not a zero.
 *
 * There is deliberately no cross-engine row total: a food batch cost and a
 * haulage route cost are different financial objects, so a row sum would be an
 * invented figure. Column totals come from the engine's own published total
 * where it has one.
 */
export function SectorCostTable({
  calculations,
}: Readonly<{ calculations: readonly DashboardCalculation[] }>) {
  const columns = calculations.filter((item) => item.cost_categories.length > 0);

  if (columns.length === 0) {
    return (
      <PanelEmptyState
        title="Sektörel maliyet girdisi yok"
        description="Kayıtlı hesaplama sürümlerinde kategori bazlı maliyet dağılımı bulunmuyor. Bir sektör motoru çalıştırıldığında bu tablo dolar."
      />
    );
  }

  const cellsByColumn = columns.map((column) => {
    const merged = new Map<string, string>();
    for (const group of column.cost_categories) {
      for (const [key, amount] of group.entries) merged.set(key, amount);
    }
    return merged;
  });

  const rowKeys = [...new Set(cellsByColumn.flatMap((cells) => [...cells.keys()]))].sort();

  return (
    <div className={styles.tableScroll}>
      <table className={styles.table}>
        <caption>
          Her sütun bir sektör motorunun kendi kayıtlı sürümüdür. Motorlar arası satır toplamı
          hesaplanmaz; farklı motorların tutarları aynı finansal nesne değildir.
        </caption>
        <thead>
          <tr>
            <th scope="col">Maliyet kalemi</th>
            {columns.map((column) => (
              <th key={column.calculation_id} scope="col">
                {column.engine_title ?? column.calculation_type}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rowKeys.map((rowKey) => (
            <tr key={rowKey}>
              <th scope="row">{turkishCategoryLabel(rowKey) ?? rowKey.replaceAll("_", " ")}</th>
              {cellsByColumn.map((cells, index) => {
                const amount = cells.get(rowKey);
                const column = columns[index];
                return (
                  <td key={`${column?.calculation_id ?? index}-${rowKey}`}>
                    {amount === undefined ? (
                      <span className={styles.tableEmptyCell} title="Bu motor bu kalemi yayınlamıyor">
                        {NO_VALUE}
                      </span>
                    ) : (
                      (formatCurrency(amount) ?? amount)
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className={styles.tableTotalRow}>
            <th scope="row">Motorun yayınladığı toplam</th>
            {columns.map((column) => (
              <td key={`total-${column.calculation_id}`}>
                {column.total_cost === null ? (
                  <span
                    className={styles.tableEmptyCell}
                    title="Bu motor genel toplam yayınlamıyor"
                  >
                    {NO_VALUE}
                  </span>
                ) : (
                  (formatCurrency(column.total_cost) ?? column.total_cost)
                )}
              </td>
            ))}
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
