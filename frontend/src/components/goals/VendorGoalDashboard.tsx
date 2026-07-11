import { Target, Wallet, TrendingUp, CalendarClock, Trophy, Sparkles, Brain, Receipt, Gift } from 'lucide-react';
import {
  useMyGoalTracking, useGoalForecastCierre, useMetaSugerida, useGoalRecommendations,
  useMyCommission, usePostGoalInvoices,
} from '../../hooks/ventas';
import { KpiCard, KpiCardSkeleton } from '../ui/KpiCard';
import { ChartCard } from '../ui/ChartCard';
import { AlertBadge } from '../ui/AlertBadge';
import { GoalProgressGauge } from './GoalProgressGauge';
import { fmt, fmtMoney, pct } from '../../utils/format';
import type { NivelComision } from '../../types/ventas';

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

// Mismos 4 niveles que commission_engine.py::NivelCumplimiento -- la fuente de verdad del
// tramo es el backend, esto solo mapea la etiqueta a mostrar y su color.
const NIVEL_CONFIG: Record<NivelComision, { label: string; badgeVariant: 'critical' | 'warning' | 'info' | 'success' }> = {
  LEJOS:     { label: 'Lejos',     badgeVariant: 'critical' },
  CERCA:     { label: 'Cerca',     badgeVariant: 'warning' },
  META:      { label: 'Meta',      badgeVariant: 'info' },
  EXCELENTE: { label: 'Excelente', badgeVariant: 'success' },
};

export const VendorGoalDashboard = () => {
  const { data, loading, error } = useMyGoalTracking();
  const forecast = useGoalForecastCierre();
  const metaSugerida = useMetaSugerida();
  const recomendaciones = useGoalRecommendations();
  const comision = useMyCommission();
  const postMeta = usePostGoalInvoices();

  const metaMensual = data?.meta_mensual ?? 0;
  const ventasActuales = data?.cumplimiento_actual ?? 0;
  const cumplimientoPct = metaMensual > 0 ? (ventasActuales / metaMensual) * 100 : 0;
  const restante = Math.max(0, metaMensual - ventasActuales);
  const estado = ESTADO_CONFIG[estadoDeMeta(cumplimientoPct)];
  const metaAlcanzada = cumplimientoPct >= 100;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap justify-between items-center gap-3 animate-fade-in">
        <div>
          <h1 className="text-3xl font-display font-semibold text-slate-100">Mi Meta y Comisión</h1>
          <p className="text-sm text-slate-500 mt-0.5">Período vigente</p>
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

      {/* Medidor de progreso -- D3, tramos = umbrales reales de comisión (commission_engine.py) */}
      <ChartCard title="Progreso hacia la meta" badge={{ label: 'Live', variant: 'live' }} height="h-auto" loading={loading}>
        <div className="flex flex-col items-center gap-1 py-2">
          <GoalProgressGauge pctCumplimiento={cumplimientoPct} />
          <div className="flex flex-col items-center gap-2 -mt-2">
            <span className="font-mono text-3xl font-semibold text-slate-100">{pct(cumplimientoPct)}</span>
            <AlertBadge variant={estado.badgeVariant}>{estado.label}</AlertBadge>
          </div>
          {comision.data?.mensaje_alerta && (
            <p className={`text-sm mt-2 text-center ${comision.data.en_alerta_cierre ? 'text-amber-400' : 'text-green-400'}`}>
              {comision.data.mensaje_alerta}
            </p>
          )}
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

        {/* Meta sugerida (próximo período) -- 100% estadística, sin modelo ML (goals_rf decomisionado) */}
        <ChartCard title="Meta sugerida (próximo período)" badge={{ label: 'Estadística', variant: 'hist' }} loading={metaSugerida.loading} height="h-[220px]">
          {metaSugerida.error ? (
            <p className="text-red-400 text-sm">{metaSugerida.error}</p>
          ) : (
            <div className="flex flex-col items-center justify-center h-full gap-2">
              <Target size={20} className="text-cyan-400" />
              <span className="font-mono text-2xl font-semibold text-slate-100">
                {metaSugerida.data ? fmt(metaSugerida.data.meta_sugerida_estadistica) : '—'}
              </span>
              <span className="text-xs text-slate-500">Histórico limpio de picos (IQR) + tendencia reciente</span>
              {metaSugerida.data && (
                <p className="text-xs text-slate-500 text-center">
                  {metaSugerida.data.meses_historico_usados} meses de histórico · {metaSugerida.data.valores_atipicos_excluidos} atípicos excluidos (IQR) · {metaSugerida.data.meses_atipicos_ml_detectados} meses con transacciones atípicas (IsolationForest)
                </p>
              )}
            </div>
          )}
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Comisión -- Venta Neta real vs. meta, tramo y tasa aplicada (commission_engine.py) */}
        <ChartCard
          title="Comisión"
          badge={{ label: comision.data ? NIVEL_CONFIG[comision.data.nivel].label : '—', variant: 'live' }}
          loading={comision.loading}
          height="h-[220px]"
        >
          {comision.error ? (
            <p className="text-red-400 text-sm">{comision.error}</p>
          ) : (
            <div className="grid grid-cols-2 gap-4 h-full items-center">
              <div className="flex flex-col items-center text-center gap-1">
                <Wallet size={20} className="text-green-400" />
                <span className="font-mono text-2xl font-semibold text-slate-100">
                  {comision.data ? fmtMoney(comision.data.comision_devengada) : '—'}
                </span>
                <span className="text-xs text-slate-500">Comisión devengada</span>
              </div>
              <div className="flex flex-col items-center text-center gap-1">
                <TrendingUp size={20} className="text-cyan-400" />
                <span className="font-mono text-2xl font-semibold text-slate-100">
                  {comision.data ? `${comision.data.tasa_aplicada_pct.toFixed(2)}%` : '—'}
                </span>
                <span className="text-xs text-slate-500">Tasa aplicada</span>
              </div>
              {comision.data && comision.data.bono_aplicado > 0 && (
                <div className="col-span-2 flex items-center justify-center gap-2 text-sm text-amber-400">
                  <Gift size={14} />
                  <span>Incluye bono de sobrecumplimiento: {fmtMoney(comision.data.bono_aplicado)}</span>
                </div>
              )}
              {comision.data && (
                <p className="col-span-2 text-xs text-slate-500 text-center">
                  Venta Neta {fmtMoney(comision.data.venta_real)} de meta {fmtMoney(comision.data.monto_meta)}
                </p>
              )}
            </div>
          )}
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
          badge={{ label: 'Live', variant: 'live' }}
          loading={postMeta.loading}
          height="h-[240px]"
        >
          <div className="flex flex-col h-full gap-3">
            <div className="flex items-center justify-center gap-2">
              <Trophy size={20} className="text-amber-400" />
              <AlertBadge variant="success">¡Meta alcanzada este período!</AlertBadge>
            </div>
            {postMeta.error ? (
              <p className="text-red-400 text-sm text-center">{postMeta.error}</p>
            ) : postMeta.data.length === 0 ? (
              <p className="text-slate-500 text-sm text-center mt-4">Aún no hay facturas registradas después de cruzar la meta.</p>
            ) : (
              <ul className="space-y-1.5 overflow-auto flex-1">
                {postMeta.data.map((f) => (
                  <li key={f.num_factura} className="flex justify-between items-center py-1.5 border-b border-slate-800 last:border-0">
                    <div className="flex items-center gap-1.5">
                      <Receipt size={13} className="text-cyan-400" />
                      <span className="text-sm font-mono text-slate-200">{f.num_factura}</span>
                      <span className="text-xs text-slate-500">{f.fecha}</span>
                    </div>
                    <span className="text-sm font-mono text-slate-300">{fmtMoney(f.monto_factura)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </ChartCard>
      )}
    </div>
  );
};
