import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { Loader2 } from 'lucide-react';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'outline' | 'success' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  loading?: boolean;
  icon?: ReactNode;
  iconRight?: ReactNode;
  children: ReactNode;
}

const variants = {
  primary: 'bg-primary text-white border border-primary hover:bg-accent hover:border-accent disabled:hover:bg-primary',
  secondary: 'bg-bg-hover text-text-primary border border-border-strong hover:bg-bg-elevated',
  ghost: 'bg-transparent text-slate-300 border border-slate-700 hover:border-primary hover:text-primary',
  outline: 'bg-transparent text-primary border border-primary/40 hover:bg-primary/10',
  success: 'bg-success text-white border border-success hover:bg-success/90 disabled:hover:bg-success',
  danger: 'bg-danger/90 text-white border border-danger/90 hover:bg-danger hover:border-danger disabled:hover:bg-danger/90',
};

const sizes = {
  sm: 'px-3 py-1.5 text-xs gap-1.5',
  md: 'px-4 py-2 text-sm gap-2',
  lg: 'px-5 py-2.5 text-base gap-2',
};

/** Botón base del sistema (P2): variantes primary/ghost/danger, foco accesible,
 * estado loading con spinner embebido. Reemplaza los `<button className="...">`
 * improvisados por página. */
export const Button = ({
  variant = 'ghost', size = 'md', loading = false, icon, children, className = '',
  disabled, ...rest
}: ButtonProps) => (
  <button
    type="button"
    disabled={disabled || loading}
    className={`inline-flex items-center justify-center font-semibold rounded-lg transition-colors duration-150 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed focus-ring ${variants[variant]} ${sizes[size]} ${className}`}
    {...rest}
  >
    {loading ? <Loader2 size={size === 'sm' ? 14 : 16} className="animate-spin" /> : icon}
    {children}
  </button>
);
