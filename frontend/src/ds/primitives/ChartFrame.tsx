import { useId, useState, type ReactNode } from "react";

export interface ChartTable { columns: string[]; rows: (string | number)[][] }

/** Accessible wrapper every chart uses: text summary + data-table toggle. */
export function ChartFrame({ title, summary, table, children }: {
  title: string; summary: string; table: ChartTable; children: ReactNode;
}) {
  const [asTable, setAsTable] = useState(false);
  const summaryId = useId();
  return (
    <figure className="tl-chart" aria-describedby={summaryId}>
      <figcaption className="tl-chart__head">
        <span className="tl-chart__title">{title}</span>
        <button type="button" className="tl-chart__toggle" aria-pressed={asTable} onClick={() => setAsTable((v) => !v)}>
          Show as table
        </button>
      </figcaption>
      <p id={summaryId} className="tl-sr-only">{summary}</p>
      {asTable ? (
        <table className="tl-chart__table">
          <thead><tr>{table.columns.map((c) => <th key={c} scope="col">{c}</th>)}</tr></thead>
          <tbody>
            {table.rows.map((row, i) => (
              <tr key={i}>{row.map((cell, j) => <td key={j}>{cell}</td>)}</tr>
            ))}
          </tbody>
        </table>
      ) : children}
    </figure>
  );
}
