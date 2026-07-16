import type { ReactNode } from 'react';
import { EmptyState } from './EmptyState';
import { ErrorState } from './ErrorState';

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

export const ChartCard = ({
  title, badge, actions, children, className = '', height = 'h-[320px]', loading = false,
  error, onRetry, empty = false, emptyTitle = 'Sin datos para este período', emptyDescription,
}: ChartCardProps) => (
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
      </div>
    </div>
    <div className={`${height} overflow-hidden`}>
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
  </div>
);
