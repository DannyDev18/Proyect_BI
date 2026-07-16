import type { ReactNode } from 'react';
import { useMemo, useState } from 'react';
import { ArrowDown, ArrowUp, ChevronsUpDown } from 'lucide-react';
import { EmptyState } from './EmptyState';
import { ErrorState } from './ErrorState';

export interface DataTableColumn<T> {
  key: string;
  header: string;
  headerTitle?: string;
  render: (row: T) => ReactNode;
  numeric?: boolean;
  width?: string;
  /** Habilita orden client-side por esta columna (F5, D-8). Requiere `sortAccessor`
   * -- ordena sobre `data` ya cargada, nunca sobre queries/paginación server-side. */
  sortable?: boolean;
  sortAccessor?: (row: T) => string | number | null | undefined;
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
  /** Bajo `md`, renderiza cada fila como una card apilada (label + valor) en vez de
   * scroll horizontal (F5, D-8). Opt-in por tabla para migrar sin big-bang. */
  responsive?: boolean;
  /** Primera columna fija al hacer scroll horizontal — para matrices anchas (Bodega). */
  stickyFirstColumn?: boolean;
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

type SortDir = 'asc' | 'desc';

/** Tabla estándar del sistema (P5, F5) — cabecera sticky, densidad configurable, celdas
 * numéricas alineadas en mono, fila crítica vía `rowClassName`, orden client-side
 * opcional por columna, responsive opt-in (cards bajo `md`), y los 3 estados
 * (loading/error/empty) integrados. Sustituye las tablas HTML planas por página. */
export function DataTable<T>({
  columns, data, rowKey, density = 'normal', loading = false, error, onRetry,
  emptyTitle = 'Sin resultados', emptyDescription, emptyAction, rowClassName,
  maxHeight = 'max-h-[420px]', pagination, className = '', responsive = false,
  stickyFirstColumn = false,
}: DataTableProps<T>) {
  const cellPad = density === 'compact' ? 'px-4 py-2' : 'px-6 py-3';
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>('asc');

  const sortedData = useMemo(() => {
    if (!sortKey) return data;
    const col = columns.find((c) => c.key === sortKey);
    if (!col?.sortAccessor) return data;
    const accessor = col.sortAccessor;
    const withIndex = data.map((row, i) => ({ row, i }));
    withIndex.sort((a, b) => {
      const av = accessor(a.row);
      const bv = accessor(b.row);
      if (av == null && bv == null) return a.i - b.i;
      if (av == null) return 1;
      if (bv == null) return -1;
      const cmp = typeof av === 'number' && typeof bv === 'number'
        ? av - bv
        : String(av).localeCompare(String(bv), 'es');
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return withIndex.map((w) => w.row);
  }, [data, columns, sortKey, sortDir]);

  const toggleSort = (col: DataTableColumn<T>) => {
    if (!col.sortable || !col.sortAccessor) return;
    if (sortKey !== col.key) {
      setSortKey(col.key);
      setSortDir('asc');
    } else {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    }
  };

  const stickyCol = (index: number) => (stickyFirstColumn && index === 0 ? 'sticky left-0 z-[6] bg-bg-card' : '');

  const headerRow = (
    <tr>
      {columns.map((c, i) => (
        <th
          key={c.key}
          className={`${cellPad} ${c.numeric ? 'text-right' : ''} ${stickyCol(i)}`}
          style={c.width ? { width: c.width } : undefined}
          title={c.headerTitle}
        >
          {c.sortable && c.sortAccessor ? (
            <button
              type="button"
              onClick={() => toggleSort(c)}
              className="inline-flex items-center gap-1 hover:text-slate-300 transition-colors cursor-pointer focus-ring rounded"
            >
              {c.header}
              {sortKey === c.key ? (
                sortDir === 'asc' ? <ArrowUp size={12} /> : <ArrowDown size={12} />
              ) : (
                <ChevronsUpDown size={12} className="opacity-50" />
              )}
            </button>
          ) : (
            c.header
          )}
        </th>
      ))}
    </tr>
  );

  return (
    <div className={`card overflow-hidden ${className}`}>
      {/* Vista tabla — oculta bajo `md` cuando `responsive` está activo (F5, D-8) */}
      <div className={`overflow-x-auto ${maxHeight} overflow-y-auto ${responsive ? 'hidden md:block' : ''}`}>
        <table className="w-full text-left text-sm whitespace-nowrap">
          <thead className="bg-slate-950/60 text-slate-500 text-xs uppercase tracking-widest sticky top-0 z-10">
            {headerRow}
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
            {!loading && !error && sortedData.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="p-0">
                  <EmptyState title={emptyTitle} description={emptyDescription} action={emptyAction} />
                </td>
              </tr>
            )}
            {!loading && !error && sortedData.map((row) => (
              <tr
                key={rowKey(row)}
                className={`animate-row-fade hover:bg-bg-hover transition-colors ${rowClassName?.(row) ?? ''}`}
              >
                {columns.map((c, i) => (
                  <td key={c.key} className={`${cellPad} ${c.numeric ? 'text-right font-mono' : ''} ${stickyCol(i)}`}>
                    {c.render(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Vista cards — solo bajo `md` cuando `responsive` está activo */}
      {responsive && (
        <div className="md:hidden divide-y divide-slate-800/80">
          {loading && Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="p-4 space-y-2">
              <div className="skeleton h-4 w-2/3 rounded" />
              <div className="skeleton h-4 w-1/2 rounded" />
            </div>
          ))}
          {!loading && error && <ErrorState message={error} onRetry={onRetry} />}
          {!loading && !error && sortedData.length === 0 && (
            <EmptyState title={emptyTitle} description={emptyDescription} action={emptyAction} />
          )}
          {!loading && !error && sortedData.map((row) => (
            <div key={rowKey(row)} className={`animate-row-fade p-4 space-y-2 ${rowClassName?.(row) ?? ''}`}>
              {columns.map((c) => (
                <div key={c.key} className="flex items-start justify-between gap-3 text-sm">
                  <span className="text-xs uppercase tracking-wider text-slate-500 flex-shrink-0 pt-0.5">{c.header}</span>
                  <span className={c.numeric ? 'font-mono text-right' : 'text-right'}>{c.render(row)}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      {pagination}
    </div>
  );
}
