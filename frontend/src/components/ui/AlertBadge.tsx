interface AlertBadgeProps {
  variant: 'critical' | 'warning' | 'info' | 'success' | 'neutral';
  children: React.ReactNode;
  className?: string;
  dot?: boolean;
}

const variants = {
  critical: 'bg-danger/10  text-danger    border border-danger/25',
  warning:  'bg-warning/10 text-warning  border border-warning/25',
  info:     'bg-info/10  text-info   border border-info/25',
  success:  'bg-success/10 text-success  border border-success/25',
  neutral:  'bg-slate-700/30 text-slate-400  border border-slate-600/20',
};

const dotColors = {
  critical: 'bg-danger',
  warning:  'bg-warning',
  info:     'bg-info',
  success:  'bg-success',
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
