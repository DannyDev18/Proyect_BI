import type { ReactNode } from 'react';
import { EmptyState } from './EmptyState';
import { ErrorState } from './ErrorState';

export interface DataTableColumn<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  numeric?: boolean;
  width?: string;
}

interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  data: T[];
  rowKey: (row: T) => string | number;
  density?: 'normal' | 'compact';
  loading?: boolean;
  error?: string;
  onRetry?: () => void;
  emptyTitle?: string;
  emptyDescription?: string;
  emptyAction?: ReactNode;
  rowClassName?: (row: T) => string;
  maxHeight?: string;
  pagination?: ReactNode;
  className?: string;
}

const SkeletonRows = ({ columns, density }: { columns: number; density: 'normal' | 'compact' }) => (
  <>
    {Array.from({ length: 6 }).map((_, i) => (
      <tr key={i}>
        {Array.from({ length: columns }).map((__, j) => (
          <td key={j} className={density === 'compact' ? 'px-4 py-2' : 'px-6 py-3'}>
            <div className="skeleton h-4 w-full max-w-[140px] rounded" />
          </td>
        ))}
      </tr>
    ))}
  </>
);

/** Tabla estándar del sistema (P5) — cabecera sticky, densidad configurable, celdas
 * numéricas alineadas en mono, fila crítica vía `rowClassName`, y los 3 estados
 * (loading/error/empty) integrados. Sustituye las tablas HTML planas por página. */
export function DataTable<T>({
  columns, data, rowKey, density = 'normal', loading = false, error, onRetry,
  emptyTitle = 'Sin resultados', emptyDescription, emptyAction, rowClassName,
  maxHeight = 'max-h-[420px]', pagination, className = '',
}: DataTableProps<T>) {
  const cellPad = density === 'compact' ? 'px-4 py-2' : 'px-6 py-3';

  return (
    <div className={`card overflow-hidden ${className}`}>
      <div className={`overflow-x-auto ${maxHeight} overflow-y-auto`}>
        <table className="w-full text-left text-sm whitespace-nowrap">
          <thead className="bg-slate-950/60 text-slate-500 text-xs uppercase tracking-widest sticky top-0 z-10">
            <tr>
              {columns.map((c) => (
                <th key={c.key} className={`${cellPad} ${c.numeric ? 'text-right' : ''}`} style={c.width ? { width: c.width } : undefined}>
                  {c.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/80">
            {loading && <SkeletonRows columns={columns.length} density={density} />}
            {!loading && error && (
              <tr>
                <td colSpan={columns.length} className="p-0">
                  <ErrorState message={error} onRetry={onRetry} />
                </td>
              </tr>
            )}
            {!loading && !error && data.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="p-0">
                  <EmptyState title={emptyTitle} description={emptyDescription} action={emptyAction} />
                </td>
              </tr>
            )}
            {!loading && !error && data.map((row) => (
              <tr
                key={rowKey(row)}
                className={`animate-row-fade hover:bg-slate-800/20 transition-colors ${rowClassName?.(row) ?? ''}`}
              >
                {columns.map((c) => (
                  <td key={c.key} className={`${cellPad} ${c.numeric ? 'text-right font-mono' : ''}`}>
                    {c.render(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pagination}
    </div>
  );
}
