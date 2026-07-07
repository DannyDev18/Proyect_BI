interface ChartCardProps {
  title: string;
  badge?: { label: string; variant?: 'live' | 'ml' | 'hist' };
  children: React.ReactNode;
  className?: string;
  height?: string;
  loading?: boolean;
}

const badgeStyles = {
  live: 'bg-green-500/10 text-green-400 border border-green-500/20',
  ml:   'bg-cyan-500/10  text-cyan-400  border border-cyan-500/20',
  hist: 'bg-slate-700/40 text-slate-400 border border-slate-600/20',
};

const ChartSkeleton = ({ height }: { height: string }) => (
  <div className={`${height} flex flex-col gap-2 justify-end`}>
    <div className="skeleton h-full rounded-md" />
  </div>
);

export const ChartCard = ({
  title, badge, children, className = '', height = 'h-[320px]', loading = false,
}: ChartCardProps) => (
  <div className={`card p-6 animate-fade-in ${className}`}>
    <div className="flex items-center justify-between mb-6">
      <h3 className="text-base font-semibold text-slate-200 font-display">{title}</h3>
      {badge && (
        <span className={`text-xs px-2.5 py-1 rounded-full font-semibold ${badgeStyles[badge.variant ?? 'hist']}`}>
          {badge.variant === 'live' && <span className="inline-block w-1.5 h-1.5 rounded-full bg-green-400 mr-1.5 animate-pulse-slow" />}
          {badge.label}
        </span>
      )}
    </div>
    <div className={height}>
      {loading ? <ChartSkeleton height={height} /> : children}
    </div>
  </div>
);
