import type { ReactNode } from 'react';

interface FilterBarProps {
  children: ReactNode;
  className?: string;
}

/** Contenedor estándar de filtros (F6, D-10): absorbe el `bg-slate-800/50` a mano de
 * Gerencia; `BodegaFilterBar` lo adopta como wrapper. Un solo lenguaje visual para
 * las barras de filtros de los 4 dashboards. */
export const FilterBar = ({ children, className = '' }: FilterBarProps) => (
  <div className={`card p-4 flex flex-wrap items-end gap-3 animate-fade-in ${className}`}>
    {children}
  </div>
);

interface FilterFieldProps {
  label: string;
  htmlFor?: string;
  className?: string;
  children: ReactNode;
}

/** Label + control dentro de una `FilterBar`, mismo estilo de etiqueta en todos los filtros. */
export const FilterField = ({ label, htmlFor, className = '', children }: FilterFieldProps) => (
  <div className={`flex flex-col gap-1 ${className}`}>
    <label htmlFor={htmlFor} className="text-[11px] uppercase tracking-widest text-slate-500">{label}</label>
    {children}
  </div>
);
