import { KpiCard, KpiCardSkeleton } from '../ui/KpiCard';
import { ErrorState } from '../ui/ErrorState';
import { TrendingUp, Eye, CheckCircle2 } from 'lucide-react';
import { useCrossSellKpis } from '../../hooks/crossSelling';
import { pct } from '../../utils/format';

/** KPI de conversión del módulo de Venta Cruzada (RN-CS2): mostradas vs aceptadas.
 * Reutilizable en Ventas y Gerencia (docs/features/plan_modulo_cross_selling.md §2.5). */
export const CrossSellKpiPanel = () => {
  const kpis = useCrossSellKpis();

  if (kpis.loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <KpiCardSkeleton /><KpiCardSkeleton /><KpiCardSkeleton />
      </div>
    );
  }
  if (kpis.error) {
    return (
      <div className="card p-6">
        <ErrorState message={kpis.error} onRetry={kpis.refetch} />
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <KpiCard title="Sugerencias Mostradas" value={kpis.data?.sugerencias_mostradas ?? 0} icon={Eye} trend="neutral" />
      <KpiCard title="Sugerencias Aceptadas" value={kpis.data?.sugerencias_aceptadas ?? 0} icon={CheckCircle2} trend="neutral" />
      <KpiCard title="Tasa de Conversión" value={kpis.data ? pct(kpis.data.tasa_conversion_pct) : '—'} icon={TrendingUp} trend={kpis.data && kpis.data.tasa_conversion_pct >= 20 ? 'up' : 'neutral'} />
    </div>
  );
};
