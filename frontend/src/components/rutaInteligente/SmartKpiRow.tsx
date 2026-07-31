import { AlertTriangle, TrendingDown, Target, Gauge } from 'lucide-react';
import { KpiCard, KpiCardSkeleton } from '../ui/KpiCard';
import type { TarjetasHeader } from '../../types/cartera360';

const money = (n: number) => n.toLocaleString('es-EC', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });

interface SmartKpiRowProps {
  tarjetas: TarjetasHeader | null;
  loading: boolean;
}

/** Tarjetas inteligentes accionables (§4.1 del plan). Reducidas a 4 (feedback de
 * usuario 2026-07-28: 8 tarjetas eran demasiadas para una lectura rápida al abrir el
 * módulo) -- se conservan las 4 que disparan una acción concreta ese mismo día: cuántos
 * clientes necesitan atención, cuánto ingreso está en juego, cuánto se puede ganar hoy y
 * cómo va el día contra la meta. `clientes_asignados`, `clientes_recuperados_mes` y
 * `oportunidades_activas` siguen calculándose en el backend (`TarjetasHeader`, sin
 * cambio de contrato) mostrarse en otro lugar si se decide -- solo se retiran de esta
 * fila, ningún dato se descarta. `objetivo_diario` se fusiona como referencia dentro de
 * "Avance del día" en vez de ocupar una tarjeta propia. */
export const SmartKpiRow = ({ tarjetas, loading }: SmartKpiRowProps) => {
  if (loading || !tarjetas) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => <KpiCardSkeleton key={i} />)}
      </div>
    );
  }

  const avancePct = tarjetas.objetivo_diario ? (tarjetas.avance_dia / tarjetas.objetivo_diario) * 100 : null;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <KpiCard
        title="Clientes con alerta hoy" value={tarjetas.clientes_con_alerta} icon={AlertTriangle}
        state={tarjetas.clientes_con_alerta > 0 ? 'warning' : undefined}
        tooltip="Riesgo alto del modelo churn_rf, sobre el shortlist enriquecido de la cartera."
      />
      <KpiCard
        title="Ingreso potencial en riesgo" value={money(tarjetas.ingreso_potencial_en_riesgo)} icon={TrendingDown}
        state="danger"
        tooltip="Σ (valor histórico × probabilidad de abandono) del shortlist enriquecido."
      />
      <KpiCard
        title="Valor potencial de la ruta de hoy" value={money(tarjetas.valor_potencial_ruta_hoy)} icon={Target}
        tooltip="Suma del ticket promedio real de los clientes de la ruta -- un potencial, no una venta prometida."
      />
      <KpiCard
        title="Avance del día"
        value={money(tarjetas.avance_dia)}
        subValue={
          avancePct !== null
            ? `${avancePct.toFixed(0)}% de la meta diaria (${money(tarjetas.objetivo_diario as number)})`
            : 'Sin meta mensual generada'
        }
        trend={avancePct !== null ? (avancePct >= 100 ? 'up' : 'neutral') : 'neutral'}
        icon={Gauge}
      />
    </div>
  );
};
