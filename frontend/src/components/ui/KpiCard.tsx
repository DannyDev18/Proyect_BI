import type { LucideIcon } from 'lucide-react';

interface KpiCardProps {
  title: string;
  value: string | number;
  subValue?: string;
  icon: LucideIcon;
  trend?: 'up' | 'down' | 'neutral';
  className?: string;
  animDelay?: number;
}

const trendConfig = {
  up:      { bg: 'bg-cyan-500/10 border-cyan-500/20', text: 'text-cyan-400', icon: '↑' },
  down:    { bg: 'bg-red-500/10  border-red-500/20',  text: 'text-red-400',  icon: '↓' },
  neutral: { bg: 'bg-slate-700/30 border-slate-600/20', text: 'text-slate-400', icon: '—' },
};

export const KpiCard = ({
  title, value, subValue, icon: Icon, trend = 'neutral', animDelay = 0,
}: KpiCardProps) => {
  const t = trendConfig[trend];
  return (
    <div
      className="animate-fade-in-up card card-hover p-6 group relative"
      style={{ animationDelay: `${animDelay}ms` }}
    >
      <div className="flex justify-between items-start mb-4 relative z-10">
        <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">{title}</p>
        <div className={`p-2.5 rounded-xl border ${t.bg}`}>
          <Icon size={18} className={t.text} />
        </div>
      </div>

      <div className="relative z-10">
        <p className="font-mono text-3xl font-semibold text-slate-100 tracking-tight">{value}</p>
        {subValue && (
          <p className={`mt-2 text-xs font-medium ${t.text}`}>
            {trend !== 'neutral' && <span className="mr-1">{t.icon}</span>}
            {subValue}
          </p>
        )}
      </div>
    </div>
  );
};

// Skeleton variant while loading
export const KpiCardSkeleton = () => (
  <div className="card p-6">
    <div className="flex justify-between mb-4">
      <div className="skeleton h-3 w-28 rounded" />
      <div className="skeleton h-8 w-8 rounded-xl" />
    </div>
    <div className="skeleton h-8 w-32 rounded mb-2" />
    <div className="skeleton h-3 w-20 rounded" />
  </div>
);
