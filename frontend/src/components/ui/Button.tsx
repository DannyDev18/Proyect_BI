import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { Loader2 } from 'lucide-react';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'ghost' | 'danger';
  size?: 'sm' | 'md';
  loading?: boolean;
  icon?: ReactNode;
  children: ReactNode;
}

const variants = {
  primary: 'bg-cyan-600 text-white border border-cyan-600 hover:bg-cyan-500 hover:border-cyan-500 disabled:hover:bg-cyan-600',
  ghost: 'bg-transparent text-slate-300 border border-slate-700 hover:border-cyan-500 hover:text-cyan-400',
  danger: 'bg-red-600/90 text-white border border-red-600/90 hover:bg-red-500 hover:border-red-500 disabled:hover:bg-red-600/90',
};

const sizes = {
  sm: 'px-3 py-1.5 text-xs gap-1.5',
  md: 'px-4 py-2 text-sm gap-2',
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
