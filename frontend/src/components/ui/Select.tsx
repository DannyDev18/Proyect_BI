import type { SelectHTMLAttributes } from 'react';
import { ChevronDown } from 'lucide-react';

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  size?: 'sm' | 'md';
}

const sizes = {
  sm: 'pl-2.5 pr-7 py-1 text-xs',
  md: 'pl-3 pr-8 py-2 text-sm',
};

/** Wrapper estilizado del <select> nativo (P2) — sin librería, chevron lucide y
 * foco accesible. Usar `size="sm"` en toolbars de gráfico. */
export const Select = ({ size = 'md', className = '', children, ...rest }: SelectProps) => (
  <div className="relative inline-block">
    <select
      className={`appearance-none bg-slate-950 border border-slate-700 text-slate-300 rounded-md outline-none cursor-pointer hover:border-slate-600 focus-ring ${sizes[size]} ${className}`}
      {...rest}
    >
      {children}
    </select>
    <ChevronDown
      size={size === 'sm' ? 12 : 14}
      className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-slate-500"
    />
  </div>
);
