import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Select } from './Select';

interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  onPageSizeChange?: (size: number) => void;
  pageSizeOptions?: number[];
  className?: string;
}

/** Paginador global reutilizable (docs/auditoria/24_prediccion_categoria_paginacion.md):
 * « ‹ pág › » + "X–Y de Z" + selector de tamaño. Estilo consistente con las tablas de
 * Bodega (slate/cyan). */
export const Pagination = ({
  page, pageSize, total, totalPages, onPageChange, onPageSizeChange,
  pageSizeOptions = [10, 25, 50], className = '',
}: PaginationProps) => {
  const desde = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const hasta = Math.min(page * pageSize, total);

  return (
    <div className={`flex flex-wrap items-center justify-between gap-3 px-6 py-3 border-t border-slate-800 text-xs text-slate-500 ${className}`}>
      <div className="flex items-center gap-3">
        <span>{total === 0 ? 'Sin resultados' : `${desde}–${hasta} de ${total}`}</span>
        {onPageSizeChange && (
          <Select
            size="sm"
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            aria-label="Elementos por página"
          >
            {pageSizeOptions.map((n) => (
              <option key={n} value={n}>{n} / página</option>
            ))}
          </Select>
        )}
      </div>
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => onPageChange(Math.max(1, page - 1))}
          disabled={page <= 1}
          aria-label="Página anterior"
          className="p-1.5 rounded-md border border-slate-700 text-slate-400 disabled:opacity-30 disabled:cursor-not-allowed hover:border-primary hover:text-primary transition-colors cursor-pointer focus-ring"
        >
          <ChevronLeft size={14} />
        </button>
        <span className="px-2 font-mono text-slate-400">
          {totalPages === 0 ? '0 / 0' : `${page} / ${totalPages}`}
        </span>
        <button
          type="button"
          onClick={() => onPageChange(Math.min(totalPages || 1, page + 1))}
          disabled={page >= totalPages}
          aria-label="Página siguiente"
          className="p-1.5 rounded-md border border-slate-700 text-slate-400 disabled:opacity-30 disabled:cursor-not-allowed hover:border-primary hover:text-primary transition-colors cursor-pointer focus-ring"
        >
          <ChevronRight size={14} />
        </button>
      </div>
    </div>
  );
};
