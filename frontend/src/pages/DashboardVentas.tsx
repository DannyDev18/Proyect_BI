import { useState } from 'react';
import { Target, Users, TrendingDown, BarChart2 } from 'lucide-react';
import { useSalesGoals, useChurnRisk, useRecommendations, useCustomerSegment } from '../hooks/ventas';
import { KpiCard, KpiCardSkeleton } from '../components/ui/KpiCard';
import { ChartCard } from '../components/ui/ChartCard';
import { AlertBadge } from '../components/ui/AlertBadge';
import { ErrorState } from '../components/ui/ErrorState';
import { SearchInput } from '../components/ui/SearchInput';
import { GlobalBranchSelector } from '../components/ui/GlobalBranchSelector';
import { SaleAssistant } from '../components/crossSelling/SaleAssistant';
import { useAuthStore } from '../store/authStore';
import { pct } from '../utils/format';

// ─── Gauge: churn probability bar ────────────────────────────────────────────
const ChurnGauge = ({ prob }: { prob: number }) => {
  const p = Math.min(100, Math.max(0, prob * 100));
  const color = p >= 70 ? 'bg-red-500' : p >= 40 ? 'bg-amber-400' : 'bg-green-500';
  const label = p >= 70 ? 'Riesgo Alto' : p >= 40 ? 'Riesgo Moderado' : 'Riesgo Bajo';
  const variant = p >= 70 ? 'critical' : p >= 40 ? 'warning' : 'success';
  return (
    <div className="space-y-3">
      <div className="flex justify-between items-center">
        <span className="font-mono text-3xl font-semibold text-slate-100">{p.toFixed(1)}%</span>
        <AlertBadge variant={variant}>{label}</AlertBadge>
      </div>
      <div className="h-3 bg-slate-800 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${color}`}
          style={{ width: `${p}%` }}
        />
      </div>
      <p className="text-xs text-slate-500">Probabilidad de abandono estimada por el modelo ML</p>
    </div>
  );
};

// ─── Segment chip ─────────────────────────────────────────────────────────────
const segmentVariant = (nombre: string): 'success' | 'info' | 'warning' | 'critical' => {
  const n = nombre.toLowerCase();
  if (n.includes('vip') || n.includes('leal')) return 'success';
  if (n.includes('nuevo')) return 'info';
  if (n.includes('riesgo') || n.includes('inactiv')) return 'critical';
  return 'warning';
};

export const DashboardVentas = () => {
  const { user } = useAuthStore();
  const goals = useSalesGoals();
  const churn = useChurnRisk();
  const recs  = useRecommendations();
  const seg   = useCustomerSegment();

  const [clienteId, setClienteId] = useState('');
  const [sucursal, setSucursal] = useState<string | null>(null);

  const handleSearch = (val: string) => {
    setClienteId(val);
    churn.execute(val);
    recs.execute(val);
    seg.execute(val);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap justify-between items-center gap-3 animate-fade-in">
        <div>
          <h1 className="text-3xl font-display font-semibold text-slate-100">Gestión Comercial</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Sucursal: <span className="text-slate-300">{user?.role === 'gerencia' || user?.role === 'administrador' ? (sucursal || 'Consolidado Global') : (user?.sucursalId ?? 'Central')}</span> · Metas, segmentación RFM y predicciones
          </p>
        </div>
        <div className="flex items-center gap-4">
          <GlobalBranchSelector onSelectSucursal={setSucursal} />
          <AlertBadge variant="info" dot>ML Activo — K-Means + Random Forest</AlertBadge>
        </div>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        {goals.loading ? (
          <><KpiCardSkeleton /><KpiCardSkeleton /><KpiCardSkeleton /><KpiCardSkeleton /></>
        ) : goals.error ? (
          <div className="col-span-full card">
            <ErrorState message={goals.error} onRetry={goals.refetch} />
          </div>
        ) : (
          <>
            <KpiCard title="Meta Mensual" value={goals.data ? `$${(goals.data.meta_mensual/1000).toFixed(0)}k` : '—'} icon={Target} trend="neutral" animDelay={0} />
            <KpiCard title="Ventas Actuales" value={goals.data ? `$${(goals.data.ventas_actuales/1000).toFixed(0)}k` : '—'} icon={BarChart2} trend={goals.data && goals.data.ventas_actuales >= goals.data.meta_mensual * 0.9 ? 'up' : 'down'} animDelay={60} />
            <KpiCard title="Cumplimiento" value={goals.data ? pct(goals.data.cumplimiento_pct) : '—'} icon={TrendingDown} trend={goals.data && goals.data.cumplimiento_pct >= 80 ? 'up' : 'down'} animDelay={120} />
            <KpiCard title="Clientes Activos" value={goals.data?.clientes_activos ?? '—'} icon={Users} trend="neutral" animDelay={180} />
          </>
        )}
      </div>

      {/* Buscador de cliente */}
      <div className="card p-6 animate-fade-in-up stagger-1">
        <h3 className="font-sans font-semibold text-slate-200 mb-4">Análisis Individual de Cliente</h3>
        <SearchInput
          placeholder="Ingresa el ID del cliente (ej: CLI-00123)"
          onSearch={handleSearch}
          loading={churn.loading || recs.loading || seg.loading}
          label="Buscar cliente"
        />
      </div>

      {/* Results grid — visible only after a search */}
      {clienteId && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 animate-fade-in">
          {/* Segmento RFM */}
          <ChartCard
            title="Segmento RFM"
            badge={{ label: 'K-Means', variant: 'ml' }}
            loading={seg.loading}
            error={seg.error ?? undefined}
            onRetry={() => seg.execute(clienteId)}
            empty={!seg.loading && !seg.error && !seg.data}
            emptyTitle="Sin datos aún"
            emptyDescription="Busca un cliente para ver su segmento RFM."
          >
            {seg.data && (
              <div className="flex flex-col items-center justify-center h-full gap-4">
                <AlertBadge variant={segmentVariant(seg.data.nombre_segmento)} className="text-base px-4 py-2">
                  {seg.data.nombre_segmento}
                </AlertBadge>
                <p className="text-xs text-slate-500 font-mono">Cluster #{seg.data.segmento} · Cliente: {seg.data.cliente_id}</p>
              </div>
            )}
          </ChartCard>

          {/* Churn Risk */}
          <ChartCard
            title="Riesgo de Abandono (Churn)"
            badge={{ label: 'Random Forest', variant: 'ml' }}
            loading={churn.loading}
            error={churn.error ?? undefined}
            onRetry={() => churn.execute(clienteId)}
            empty={!churn.loading && !churn.error && !churn.data}
            emptyTitle="Sin datos aún"
            emptyDescription="Busca un cliente para ver su riesgo de abandono."
          >
            {churn.data && <ChurnGauge prob={churn.data.probabilidad_abandono} />}
          </ChartCard>

          {/* Recomendaciones Cross-selling */}
          <ChartCard
            title="Recomendaciones de Venta Cruzada"
            badge={{ label: 'Reglas Asociación', variant: 'ml' }}
            loading={recs.loading}
            error={recs.error ?? undefined}
            onRetry={() => recs.execute(clienteId)}
            empty={!recs.loading && !recs.error && !recs.data?.recomendaciones?.length}
            emptyTitle="Sin recomendaciones"
            emptyDescription="No hay productos sugeridos de venta cruzada para este cliente."
          >
            {recs.data?.recomendaciones?.length ? (
              <ul className="space-y-2 overflow-auto max-h-[260px]">
                {recs.data.recomendaciones.map((r, i) => (
                  <li key={i} className="flex justify-between items-center py-2 border-b border-slate-800 last:border-0">
                    <div>
                      <p className="text-sm font-medium text-slate-200">{r.nombre ?? r.producto_cod}</p>
                      <p className="text-xs text-slate-500 font-mono">{r.producto_cod}</p>
                    </div>
                    {r.confianza != null && (
                      <AlertBadge variant="info">{(r.confianza * 100).toFixed(0)}%</AlertBadge>
                    )}
                  </li>
                ))}
              </ul>
            ) : null}
          </ChartCard>
        </div>
      )}

      {/* Asistente de Venta Cruzada (docs/auditoria/25_modulo_cross_selling.md) */}
      <SaleAssistant clienteId={clienteId || null} />
    </div>
  );
};
