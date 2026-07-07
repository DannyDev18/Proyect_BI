interface AlertBadgeProps {
  variant: 'critical' | 'warning' | 'info' | 'success' | 'neutral';
  children: React.ReactNode;
  className?: string;
  dot?: boolean;
}

const variants = {
  critical: 'bg-red-500/10  text-red-400    border border-red-500/25',
  warning:  'bg-amber-500/10 text-amber-400  border border-amber-500/25',
  info:     'bg-cyan-500/10  text-cyan-400   border border-cyan-500/25',
  success:  'bg-green-500/10 text-green-400  border border-green-500/25',
  neutral:  'bg-slate-700/30 text-slate-400  border border-slate-600/20',
};

const dotColors = {
  critical: 'bg-red-400',
  warning:  'bg-amber-400',
  info:     'bg-cyan-400',
  success:  'bg-green-400',
  neutral:  'bg-slate-500',
};

export const AlertBadge = ({ variant, children, className = '', dot = false }: AlertBadgeProps) => (
  <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold ${variants[variant]} ${className}`}>
    {dot && (
      <span className={`inline-block w-1.5 h-1.5 rounded-full ${dotColors[variant]} animate-pulse-slow`} />
    )}
    {children}
  </span>
);
