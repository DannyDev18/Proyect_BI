import type { LucideIcon } from 'lucide-react';
import { ArrowDown, ArrowUp, Minus } from 'lucide-react';
import { AreaChart, Area, ResponsiveContainer } from 'recharts';
import { CountUp } from './CountUp';
import { Tooltip } from './Tooltip';

interface KpiCardProps {
  title: string;
  value: string | number;
  subValue?: string;
  icon: LucideIcon;
  trend?: 'up' | 'down' | 'neutral';
  /** Estado de negocio (F7): resalta el borde superior de la card, independiente del trend numérico. */
  state?: 'success' | 'warning' | 'danger';
  /** Serie ya cargada por la página (p. ej. histórico de predicción) para el mini-gráfico. Sin fetch nuevo. */
  sparkline?: number[];
  /** Explicación corta mostrada al pasar el mouse/foco sobre el título (F7). */
  tooltip?: string;
  className?: string;
}

const trendConfig = {
  up:      { bg: 'bg-info/10 border-info/20', text: 'text-info', Icon: ArrowUp },
  down:    { bg: 'bg-danger/10  border-danger/20',  text: 'text-danger',  Icon: ArrowDown },
  neutral: { bg: 'bg-slate-700/30 border-slate-600/20', text: 'text-slate-400', Icon: Minus },
};

const stateBorder = {
  success: 'bg-success',
  warning: 'bg-warning',
  danger: 'bg-danger',
};

export const KpiCard = ({
  title, value, subValue, icon: Icon, trend = 'neutral', state, sparkline, tooltip,
}: KpiCardProps) => {
  const t = trendConfig[trend];
  const TrendIcon = t.Icon;
  const sparkData = sparkline?.map((v, i) => ({ i, v }));
  const sparkGradientId = `kpiSpark-${title.replace(/[^a-zA-Z0-9]/g, '')}`;
  return (
    <div className="card card-hover p-6 group relative">
      {state && <span className={`absolute inset-x-0 top-0 h-[2px] rounded-t-xl ${stateBorder[state]}`} aria-hidden="true" />}
      <div className="flex justify-between items-start mb-4 relative z-10">
        {tooltip ? (
          <Tooltip label={tooltip} side="top">
            <p className="text-xs font-semibold uppercase tracking-widest text-slate-500 cursor-default">{title}</p>
          </Tooltip>
        ) : (
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">{title}</p>
        )}
        <div className={`p-2.5 rounded-xl border transition-shadow duration-150 group-hover:glow-accent-sm ${t.bg}`}>
          <Icon size={18} className={t.text} />
        </div>
      </div>

      <div className="relative z-10">
        <p className="font-mono text-2xl font-semibold text-slate-100 tracking-tight break-words leading-snug">
          {typeof value === 'number' ? <CountUp value={value} /> : value}
        </p>
        {subValue && (
          <p className={`mt-2 text-xs font-medium flex items-center gap-1 ${t.text}`}>
            {trend !== 'neutral' && <TrendIcon size={12} />}
            {subValue}
          </p>
        )}
      </div>

      {sparkData && sparkData.length > 1 && (
        <div className="h-10 -mx-1 mt-3 relative z-10 overflow-hidden">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={sparkData} margin={{ top: 2, right: 0, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id={sparkGradientId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--color-primary)" stopOpacity={0.35} />
                  <stop offset="95%" stopColor="var(--color-primary)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <Area
                type="monotone" dataKey="v" stroke="var(--color-primary)" strokeWidth={1.5}
                fill={`url(#${sparkGradientId})`} dot={false} isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
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
