"use client";

/**
 * Kembar tabel untuk tiap chart (table view WCAG): nilai yang sama dengan
 * grafik tetap terbaca tanpa hover/warna. Native <details> tanpa JS state.
 */

export interface DataTableColumn<Row> {
  header: string;
  /** Render sel; angka otomatis rata kanan + tabular. */
  cell: (row: Row) => string | number;
  numeric?: boolean;
}

export function DataTable<Row>({
  rows,
  columns,
  caption,
}: {
  rows: Row[];
  columns: DataTableColumn<Row>[];
  caption: string;
}) {
  return (
    <details className="mt-3 text-xs">
      <summary className="cursor-pointer select-none text-ink-muted hover:text-ink-secondary">
        Tabel data
      </summary>
      <table className="mt-2 w-full border-collapse">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-hairline text-left text-ink-muted">
            {columns.map((col) => (
              <th
                key={col.header}
                scope="col"
                className={`py-1.5 pr-3 font-medium ${col.numeric ? "text-right" : ""}`}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-b border-hairline/60 last:border-0">
              {columns.map((col) => (
                <td
                  key={col.header}
                  className={`py-1.5 pr-3 text-ink-secondary ${col.numeric ? "text-right tabular" : ""}`}
                >
                  {col.cell(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
