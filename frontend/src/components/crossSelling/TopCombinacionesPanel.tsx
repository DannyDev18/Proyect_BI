import { Link2 } from 'lucide-react';
import { KpiCardSkeleton } from '../ui/KpiCard';
import { ErrorState } from '../ui/ErrorState';
import { useCrossSellTopCombinaciones } from '../../hooks/crossSelling';

/** Top combinaciones de productos por co-ocurrencia histórica en facturas
 * (docs/auditoria/25_modulo_cross_selling.md §6.4): a diferencia de la telemetría del
 * asistente (RN-CS2), este KPI se calcula directo sobre `fact_ventas_detalle` y por eso
 * siempre tiene datos -- le da al vendedor un ejemplo concreto y ya validado de qué
 * ofrecer junto a qué, sin depender de que el asistente se haya usado antes. */
export const TopCombinacionesPanel = () => {
  const combinaciones = useCrossSellTopCombinaciones();

  if (combinaciones.loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <KpiCardSkeleton /><KpiCardSkeleton /><KpiCardSkeleton />
      </div>
    );
  }
  if (combinaciones.error) {
    return (
      <div className="card p-6">
        <ErrorState message={combinaciones.error} onRetry={combinaciones.refetch} />
      </div>
    );
  }

  const combos = combinaciones.data?.combinaciones ?? [];
  if (combos.length === 0) {
    return (
      <div className="card p-6">
        <p className="text-sm text-slate-500">
          Aún no hay suficientes facturas con 2+ productos para calcular combinaciones frecuentes.
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {combos.map((c, i) => (
        <div
          key={`${c.codart_a}-${c.codart_b}`}
          className="animate-fade-in-up card card-hover p-6 group relative"
          style={{ animationDelay: `${i * 80}ms` }}
        >
          <div className="flex justify-between items-start mb-4 relative z-10">
            <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">
              Combo #{i + 1} más vendido junto
            </p>
            <div className="p-2.5 rounded-xl border bg-cyan-500/10 border-cyan-500/20 transition-shadow duration-150 group-hover:glow-accent-sm">
              <Link2 size={18} className="text-cyan-400" />
            </div>
          </div>
          <div className="relative z-10 space-y-1">
            <p className="text-sm font-medium text-slate-200 truncate">{c.nombre_a}</p>
            <p className="text-xs text-slate-500">+</p>
            <p className="text-sm font-medium text-slate-200 truncate">{c.nombre_b}</p>
          </div>
          <p className="mt-3 text-xs font-medium text-cyan-400 relative z-10">
            {c.facturas.toLocaleString('es-EC')} facturas los llevaron juntos
          </p>
        </div>
      ))}
    </div>
  );
};
