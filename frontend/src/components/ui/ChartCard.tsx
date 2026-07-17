import type { ReactNode } from 'react';
import { useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Download, Maximize2, X } from 'lucide-react';
import { EmptyState } from './EmptyState';
import { ErrorState } from './ErrorState';
import { Tooltip } from './Tooltip';
import { exportSvgAsPng } from '../../utils/exportChart';
import { fade, fadeScale } from '../../utils/motion';

interface ChartCardProps {
  title: string;
  badge?: { label: string; variant?: 'live' | 'ml' | 'hist' };
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  height?: string;
  loading?: boolean;
  error?: string;
  onRetry?: () => void;
  empty?: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
}

// Provenance color system: live/hist = warehouse-sourced truth (cyan), ml = model-predicted (amber).
const badgeStyles = {
  live: 'bg-info/10  text-info  border border-info/20',
  hist: 'bg-info/10  text-info  border border-info/20',
  ml:   'bg-warning/10 text-warning border border-warning/20',
};

const ChartSkeleton = ({ height }: { height: string }) => (
  <div className={`${height} flex flex-col gap-2 justify-end`}>
    <div className="skeleton h-full rounded-md" />
  </div>
);

/** Card estándar para gráficas (F7, ChartCard 2.0): título + badge de procedencia +
 * acciones estándar -- fullscreen (re-render del mismo chart a tamaño completo,
 * Recharts se redimensiona vía `ResponsiveContainer`) y exportar PNG client-side
 * (serialización del SVG, sin backend ni librerías nuevas). */
export const ChartCard = ({
  title, badge, actions, children, className = '', height = 'h-[320px]', loading = false,
  error, onRetry, empty = false, emptyTitle = 'Sin datos para este período', emptyDescription,
}: ChartCardProps) => {
  const [fullscreen, setFullscreen] = useState(false);
  const chartRef = useRef<HTMLDivElement>(null);

  const handleExport = () => {
    if (chartRef.current) exportSvgAsPng(chartRef.current, title.toLowerCase().replace(/\s+/g, '-'));
  };

  const canExport = !loading && !error && !empty;
  const body = (
    <div ref={chartRef} className={`${height} overflow-hidden`}>
      {loading ? (
        <ChartSkeleton height={height} />
      ) : error ? (
        <ErrorState message={error} onRetry={onRetry} className="h-full justify-center" />
      ) : empty ? (
        <EmptyState title={emptyTitle} description={emptyDescription} className="h-full justify-center" />
      ) : (
        children
      )}
    </div>
  );

  return (
    <div className={`card p-6 animate-fade-in ${className}`}>
      <div className="flex items-center justify-between mb-6 gap-3 flex-wrap">
        <h3 className="text-base font-semibold text-slate-200 font-sans">{title}</h3>
        <div className="flex items-center gap-2">
          {actions}
          {badge && (
            <span className={`text-xs px-2.5 py-1 rounded-full font-semibold ${badgeStyles[badge.variant ?? 'hist']}`}>
              {badge.variant === 'live' && <span className="inline-block w-1.5 h-1.5 rounded-full bg-info mr-1.5 animate-pulse-slow" />}
              {badge.label}
            </span>
          )}
          {canExport && (
            <Tooltip label="Exportar PNG" side="top">
              <button
                type="button"
                onClick={handleExport}
                aria-label="Exportar gráfica como PNG"
                className="p-1.5 rounded-md text-slate-500 hover:text-slate-200 hover:bg-bg-hover transition-colors duration-fast cursor-pointer focus-ring"
              >
                <Download size={15} />
              </button>
            </Tooltip>
          )}
          {canExport && (
            <Tooltip label="Ver en pantalla completa" side="top">
              <button
                type="button"
                onClick={() => setFullscreen(true)}
                aria-label="Ver gráfica en pantalla completa"
                className="p-1.5 rounded-md text-slate-500 hover:text-slate-200 hover:bg-bg-hover transition-colors duration-fast cursor-pointer focus-ring"
              >
                <Maximize2 size={15} />
              </button>
            </Tooltip>
          )}
        </div>
      </div>
      {body}

      <AnimatePresence>
        {fullscreen && (
          <>
            <motion.div {...fade} className="fixed inset-0 z-50 bg-bg-overlay" onClick={() => setFullscreen(false)} />
            <motion.div
              {...fadeScale}
              role="dialog"
              aria-modal="true"
              aria-label={title}
              className="fixed inset-4 md:inset-12 z-50 card p-6 flex flex-col"
            >
              <div className="flex items-center justify-between mb-6 flex-shrink-0">
                <h3 className="text-lg font-semibold text-slate-200 font-sans">{title}</h3>
                <button
                  type="button"
                  onClick={() => setFullscreen(false)}
                  aria-label="Cerrar"
                  className="p-1.5 rounded-md text-slate-500 hover:text-slate-200 hover:bg-bg-hover transition-colors duration-fast cursor-pointer focus-ring"
                >
                  <X size={18} />
                </button>
              </div>
              <div className="flex-1 min-h-0">{children}</div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
};
