import type { ReactNode } from 'react';
import { useId } from 'react';

interface TooltipProps {
  label: string;
  children: ReactNode;
  side?: 'top' | 'right' | 'bottom';
  className?: string;
}

const sideClasses: Record<NonNullable<TooltipProps['side']>, string> = {
  top: 'bottom-full left-1/2 -translate-x-1/2 mb-2',
  right: 'left-full top-1/2 -translate-y-1/2 ml-2',
  bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
};

/** Tooltip CSS-first (F2, D-11): hover/foco, sin JS de posicionamiento. Uso principal:
 * sidebar colapsado (solo iconos) y acciones solo-icono en tablas. */
export const Tooltip = ({ label, children, side = 'right', className = '' }: TooltipProps) => {
  const id = useId();
  return (
    <span className={`relative inline-flex group/tooltip ${className}`}>
      <span aria-describedby={id}>{children}</span>
      <span
        id={id}
        role="tooltip"
        className={`pointer-events-none absolute z-50 whitespace-nowrap px-2.5 py-1.5 rounded-lg text-xs font-medium
          text-text-primary glass-elevated border border-border shadow-lg
          opacity-0 scale-95 transition-all duration-fast
          group-hover/tooltip:opacity-100 group-hover/tooltip:scale-100
          group-focus-within/tooltip:opacity-100 group-focus-within/tooltip:scale-100
          ${sideClasses[side]}`}
      >
        {label}
      </span>
    </span>
  );
};
