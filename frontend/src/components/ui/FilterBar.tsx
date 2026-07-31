import type { ReactNode } from 'react';

interface FilterBarProps {
  children: ReactNode;
  className?: string;
}

/** Contenedor estándar de filtros (F6, D-10): absorbe el `bg-slate-800/50` a mano de
 * Gerencia; `BodegaFilterBar` lo adopta como wrapper. Un solo lenguaje visual para
 * las barras de filtros de los 4 dashboards. Siempre en una sola fila (`flex-nowrap`):
 * antes usaba `flex-wrap`, que en viewports angostos partía los filtros en 2 filas de
 * forma desordenada (p.ej. "Almacén" solo en su propia línea en Visión Ejecutiva) --
 * con espacio insuficiente ahora se desplaza horizontalmente (`overflow-x-auto`) en
 * vez de reflowar. */
export const FilterBar = ({ children, className = '' }: FilterBarProps) => (
  <div className={`card p-4 flex flex-nowrap items-end gap-3 overflow-x-auto animate-fade-in ${className}`}>
    {children}
  </div>
);

interface FilterFieldProps {
  label: string;
  htmlFor?: string;
  className?: string;
  /** Leyenda explícita cuando un filtro se deshabilita por dependencia de otro
   * (filtros "inteligentes", Fase 2 §2.2) -- nunca se inventan opciones, se explica
   * por qué el control está vacío/deshabilitado. */
  helper?: string;
  children: ReactNode;
}

/** Label + control dentro de una `FilterBar`, mismo estilo de etiqueta en todos los filtros. */
export const FilterField = ({ label, htmlFor, className = '', helper, children }: FilterFieldProps) => (
  <div className={`flex flex-col gap-1 ${className}`}>
    <label htmlFor={htmlFor} className="text-[11px] uppercase tracking-widest text-slate-500">{label}</label>
    {children}
    {helper && <span className="text-[10px] text-slate-500">{helper}</span>}
  </div>
);
