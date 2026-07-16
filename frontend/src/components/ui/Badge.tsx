import type { ReactNode } from 'react';

type BadgeVariant = 'primary' | 'info' | 'success' | 'warning' | 'danger' | 'neutral';

interface BadgeProps {
  variant?: BadgeVariant;
  children: ReactNode;
  className?: string;
  dot?: boolean;
}

const variants: Record<BadgeVariant, string> = {
  primary: 'bg-primary/10 text-primary border border-primary/25',
  info:     'bg-info/10 text-info border border-info/25',
  success:  'bg-success/10 text-success border border-success/25',
  warning:  'bg-warning/10 text-warning border border-warning/25',
  danger:   'bg-danger/10 text-danger border border-danger/25',
  neutral:  'bg-slate-700/30 text-slate-400 border border-slate-600/20',
};

const dotColors: Record<BadgeVariant, string> = {
  primary: 'bg-primary',
  info:     'bg-info',
  success:  'bg-success',
  warning:  'bg-warning',
  danger:   'bg-danger',
  neutral:  'bg-slate-500',
};

/** Chip semántico unificado (F2, D-11): reemplaza los chips a mano por página
 * (sucursal en Header, badges de estado en tablas) y absorbe `AlertBadge`. */
export const Badge = ({ variant = 'neutral', children, className = '', dot = false }: BadgeProps) => (
  <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold ${variants[variant]} ${className}`}>
    {dot && (
      <span className={`inline-block w-1.5 h-1.5 rounded-full ${dotColors[variant]} animate-pulse-slow`} />
    )}
    {children}
  </span>
);
