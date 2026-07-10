import { Target, Wallet, TrendingUp, CalendarClock, Trophy, Sparkles, Brain } from 'lucide-react';
import { useMyGoalTracking, useGoalForecastCierre, useMetaSugerida, useGoalRecommendations } from '../../hooks/ventas';
import { KpiCard, KpiCardSkeleton } from '../ui/KpiCard';
import { ChartCard } from '../ui/ChartCard';
import { AlertBadge } from '../ui/AlertBadge';
import { useAuthStore } from '../../store/authStore';
import { fmt, pct } from '../../utils/format';

type EstadoMeta = 'riesgo' | 'cerca' | 'proxima' | 'alcanzada';

// Umbrales fijados por el diseño del dashboard vendedor (no son un cálculo de negocio
// derivado de datos -- son las bandas de estado a mostrar, ya definidas por el enunciado).
const ESTADO_CONFIG: Record<EstadoMeta, { label: string; barColor: string; badgeVariant: 'critical' | 'warning' | 'info' | 'success' }> = {
  riesgo:    { label: 'Riesgo',         barColor: 'bg-red-500',   badgeVariant: 'critical' },
  cerca:     { label: 'Cerca',          barColor: 'bg-amber-400', badgeVariant: 'warning' },
  proxima:   { label: 'Meta próxima',   barColor: 'bg-cyan-400',  badgeVariant: 'info' },
  alcanzada: { label: 'Meta alcanzada', barColor: 'bg-green-500', badgeVariant: 'success' },
};

const estadoDeMeta = (cumplimientoPct: number): EstadoMeta => {
  if (cumplimientoPct >= 100) return 'alcanzada';
  if (cumplimientoPct >= 90) return 'proxima';
  if (cumplimientoPct >= 80) return 'cerca';
  return 'riesgo';
};

const NoDisponible = ({ motivo }: { motivo: string }) => (
  <div className="flex flex-col items-center justify-center h-full gap-2 text-center px-4">
    <AlertBadge variant="neutral">Próximamente</AlertBadge>
    <p className="text-sm text-slate-500 max-w-sm">{motivo}</p>
  </div>
);

export const VendorGoalDashboard = () => {
  const { user } = useAuthStore();
  const { data, loading, error } = useMyGoalTracking();
  const forecast = useGoalForecastCierre();
  const metaSugerida = useMetaSugerida();
  const recomendaciones = useGoalRecommendations();

  const metaMensual = data?.meta_mensual ?? 0;
  const ventasActuales = data?.cumplimiento_actual ?? 0;
  const cumplimientoPct = metaMensual > 0 ? (ventasActuales / metaMensual) * 100 : 0;
  const restante = Math.max(0, metaMensual - ventasActuales);
  const estado = ESTADO_CONFIG[estadoDeMeta(cumplimientoPct)];
  const barraAnchoPct = Math.min(100, Math.max(0, cumplimientoPct));
  const metaAlcanzada = cumplimientoPct >= 100;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap justify-between items-center gap-3 animate-fade-in">
        <div>
          <h1 className="text-3xl font-display font-semibold text-slate-100">Mi Meta y Comisión</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Sucursal: <span className="text-slate-300">{user?.sucursalId ?? 'Central'}</span> · Período vigente
          </p>
        </div>
        <AlertBadge variant="info" dot>Datos en vivo — EDW</AlertBadge>
      </div>

      {error && <div className="card p-4 text-red-400 text-sm">{error}</div>}

      {/* Meta mensual */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        {loading ? (
          <><KpiCardSkeleton /><KpiCardSkeleton /><KpiCardSkeleton /><KpiCardSkeleton /></>
        ) : (
          <>
            <KpiCard title="Meta Asignada" value={fmt(metaMensual)} icon={Target} trend="neutral" animDelay={0} />
            <KpiCard title="Ventas Actuales" value={fmt(ventasActuales)} icon={TrendingUp} trend={cumplimientoPct >= 90 ? 'up' : 'down'} animDelay={60} />
            <KpiCard title="Cumplimiento" value={pct(cumplimientoPct)} icon={Wallet} trend={cumplimientoPct >= 100 ? 'up' : 'neutral'} animDelay={120} />
            <KpiCard title="Restante" value={fmt(restante)} icon={Target} trend="neutral" animDelay={180} />
          </>
        )}
      </div>

      {/* Barra de progreso */}
      <ChartCard title="Progreso hacia la meta" badge={{ label: 'Live', variant: 'live' }} height="h-auto" loading={loading}>
        <div className="space-y-3 py-2">
          <div className="flex justify-between items-center">
            <span className="font-mono text-3xl font-semibold text-slate-100">{pct(cumplimientoPct)}</span>
            <AlertBadge variant={estado.badgeVariant}>{estado.label}</AlertBadge>
          </div>
          <div className="h-3 bg-slate-800 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-700 ${estado.barColor}`}
              style={{ width: `${barraAnchoPct}%` }}
            />
          </div>
          <div className="flex justify-between text-xs text-slate-500">
            <span>&lt;80% Riesgo</span>
            <span>80-89% Cerca</span>
            <span>90-99% Meta próxima</span>
            <span>&ge;100% Meta alcanzada</span>
          </div>
        </div>
      </ChartCard>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Última semana / pronóstico de cierre -- modelo sales_rf */}
        <ChartCard title="Pronóstico de cierre del mes" badge={{ label: 'Random Forest', variant: 'ml' }} loading={forecast.loading} height="h-[220px]">
          {forecast.error ? (
            <p className="text-red-400 text-sm">{forecast.error}</p>
          ) : (
            <div className="grid grid-cols-2 gap-4 h-full items-center">
              <div className="flex flex-col items-center text-center gap-1">
                <CalendarClock size={20} className="text-cyan-400" />
                <span className="font-mono text-2xl font-semibold text-slate-100">{forecast.data?.dias_restantes ?? '—'}</span>
                <span className="text-xs text-slate-500">Días restantes</span>
              </div>
              <div className="flex flex-col items-center text-center gap-1">
                <TrendingUp size={20} className="text-cyan-400" />
                <span className="font-mono text-2xl font-semibold text-slate-100">{forecast.data ? fmt(forecast.data.proyeccion_cierre) : '—'}</span>
                <span className="text-xs text-slate-500">Proyección de cierre</span>
              </div>
              <div className="flex flex-col items-center text-center gap-1">
                <Target size={20} className="text-amber-400" />
                <span className="font-mono text-2xl font-semibold text-slate-100">{forecast.data ? pct(forecast.data.pct_cumplimiento_esperado) : '—'}</span>
                <span className="text-xs text-slate-500">% cumplimiento esperado</span>
              </div>
              <div className="flex flex-col items-center text-center gap-1">
                <Brain size={20} className="text-amber-400" />
                <span className="font-mono text-2xl font-semibold text-slate-100">
                  {forecast.data?.probabilidad_alcanzar_meta != null ? pct(forecast.data.probabilidad_alcanzar_meta) : '—'}
                </span>
                <span className="text-xs text-slate-500">Probabilidad de alcanzar la meta</span>
              </div>
            </div>
          )}
        </ChartCard>

        {/* Meta sugerida por IA vs. motor estadístico */}
        <ChartCard title="Meta sugerida (próximo período)" badge={{ label: 'IA', variant: 'ml' }} loading={metaSugerida.loading} height="h-[220px]">
          {metaSugerida.error ? (
            <p className="text-red-400 text-sm">{metaSugerida.error}</p>
          ) : (
            <div className="grid grid-cols-2 gap-4 h-full items-center">
              <div className="flex flex-col items-center text-center gap-1">
                <Brain size={20} className="text-amber-400" />
                <span className="font-mono text-2xl font-semibold text-slate-100">
                  {metaSugerida.data?.meta_sugerida_ia != null ? fmt(metaSugerida.data.meta_sugerida_ia) : '—'}
                </span>
                <span className="text-xs text-slate-500">Sugerida por IA (goals_rf)</span>
              </div>
              <div className="flex flex-col items-center text-center gap-1">
                <Target size={20} className="text-cyan-400" />
                <span className="font-mono text-2xl font-semibold text-slate-100">
                  {metaSugerida.data ? fmt(metaSugerida.data.meta_sugerida_estadistica) : '—'}
                </span>
                <span className="text-xs text-slate-500">Estadística (IQR + anomalías)</span>
              </div>
              {metaSugerida.data && (
                <p className="col-span-2 text-xs text-slate-500 text-center">
                  {metaSugerida.data.meses_historico_usados} meses de histórico · {metaSugerida.data.valores_atipicos_excluidos} atípicos excluidos (IQR) · {metaSugerida.data.meses_atipicos_ml_detectados} meses con transacciones atípicas (IsolationForest)
                </p>
              )}
            </div>
          )}
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Comisión -- todavía sin módulo de liquidación */}
        <ChartCard title="Comisión" badge={{ label: 'Pendiente', variant: 'ml' }} loading={loading} height="h-[220px]">
          <NoDisponible motivo="El cálculo de comisión estimada, comisión ganada y categorías alcanzadas requiere el módulo de liquidación de comisiones (docs/auditoria/14_fase0_analisis_modulo_metas_comisiones.md, hallazgo R-1). Aún no existe un endpoint que lo entregue." />
        </ChartCard>

        {/* Recomendaciones de productos -- reglas de asociación */}
        <ChartCard title="Productos recomendados para cerrar tu meta" badge={{ label: 'Reglas Asociación', variant: 'ml' }} loading={recomendaciones.loading} height="h-[220px]">
          {recomendaciones.error ? (
            <p className="text-red-400 text-sm">{recomendaciones.error}</p>
          ) : recomendaciones.data.length === 0 ? (
            <p className="text-slate-500 text-sm text-center mt-6">Sin recomendaciones disponibles todavía.</p>
          ) : (
            <ul className="space-y-2 overflow-auto max-h-[170px]">
              {recomendaciones.data.map((r, i) => (
                <li key={i} className="flex justify-between items-center py-2 border-b border-slate-800 last:border-0">
                  <div className="flex items-center gap-1.5">
                    <Sparkles size={13} className="text-amber-400" />
                    <p className="text-sm font-medium text-slate-200 font-mono">{r.producto_cod}</p>
                  </div>
                  <AlertBadge variant="info">lift {r.score_afinidad.toFixed(1)}</AlertBadge>
                </li>
              ))}
            </ul>
          )}
        </ChartCard>
      </div>

      {/* Facturas post-meta -- solo se muestra al alcanzar el 100% de la meta */}
      {metaAlcanzada && (
        <ChartCard
          title="Facturas post-meta"
          badge={{ label: 'Pendiente', variant: 'ml' }}
          loading={loading}
          height="h-[200px]"
        >
          <div className="flex flex-col items-center justify-center h-full gap-3 text-center px-4">
            <Trophy size={24} className="text-amber-400" />
            <AlertBadge variant="success">¡Meta alcanzada este período!</AlertBadge>
            <NoDisponible motivo="El detalle de facturas emitidas tras alcanzar la meta (factura, producto, categoría, monto y comisión generada) requiere un endpoint de detalle transaccional que aún no existe en el backend." />
          </div>
        </ChartCard>
      )}
    </div>
  );
};
