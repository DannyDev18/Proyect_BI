import type { LucideIcon } from 'lucide-react';
import { ArrowDown, ArrowUp, Minus } from 'lucide-react';
import { CountUp } from './CountUp';

interface KpiCardProps {
  title: string;
  value: string | number;
  subValue?: string;
  icon: LucideIcon;
  trend?: 'up' | 'down' | 'neutral';
  className?: string;
}

const trendConfig = {
  up:      { bg: 'bg-info/10 border-info/20', text: 'text-info', Icon: ArrowUp },
  down:    { bg: 'bg-danger/10  border-danger/20',  text: 'text-danger',  Icon: ArrowDown },
  neutral: { bg: 'bg-slate-700/30 border-slate-600/20', text: 'text-slate-400', Icon: Minus },
};

export const KpiCard = ({
  title, value, subValue, icon: Icon, trend = 'neutral',
}: KpiCardProps) => {
  const t = trendConfig[trend];
  const TrendIcon = t.Icon;
  return (
    <div className="card card-hover p-6 group relative">
      <div className="flex justify-between items-start mb-4 relative z-10">
        <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">{title}</p>
        <div className={`p-2.5 rounded-xl border transition-shadow duration-150 group-hover:glow-accent-sm ${t.bg}`}>
          <Icon size={18} className={t.text} />
        </div>
      </div>

      <div className="relative z-10">
        <p className="font-mono text-3xl font-semibold text-slate-100 tracking-tight">
          {typeof value === 'number' ? <CountUp value={value} /> : value}
        </p>
        {subValue && (
          <p className={`mt-2 text-xs font-medium flex items-center gap-1 ${t.text}`}>
            {trend !== 'neutral' && <TrendIcon size={12} />}
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
