import type { ReactNode } from 'react';
import { EmptyState } from './EmptyState';

export interface DataColumn<T> {
  key: string;
  title: string;
  width?: number | string;
  render?: (row: T) => ReactNode;
}

interface DataTableProps<T> {
  columns: DataColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  emptyTitle?: string;
  emptyDesc?: string;
}

/** 通用数据表格（支持横向滚动） */
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  emptyTitle = '暂无数据',
  emptyDesc,
}: DataTableProps<T>) {
  if (rows.length === 0) {
    return <EmptyState title={emptyTitle} desc={emptyDesc} />;
  }
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} style={c.width ? { width: c.width, minWidth: c.width } : undefined}>
                {c.title}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)}>
              {columns.map((c) => (
                <td key={c.key}>{c.render ? c.render(row) : String((row as Record<string, unknown>)[c.key] ?? '')}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}