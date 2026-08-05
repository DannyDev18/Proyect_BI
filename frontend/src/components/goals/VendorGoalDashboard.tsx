import { Target, Wallet, TrendingUp, Trophy, Sparkles, Receipt, Gift } from 'lucide-react';
import {
  useMyGoalTracking, useMetaSugerida, useGoalRecommendations,
  useMyCommission, usePostGoalInvoices,
} from '../../hooks/ventas';
import { KpiCard, KpiCardSkeleton } from '../ui/KpiCard';
import { ChartCard } from '../ui/ChartCard';
import { Badge } from '../ui/Badge';
import { GoalProgressGauge } from './GoalProgressGauge';
import { fmt, fmtMoney, pct } from '../../utils/format';

type EstadoMeta = 'riesgo' | 'cerca' | 'proxima' | 'alcanzada';

// Umbrales fijados por el diseño del dashboard vendedor (no son un cálculo de negocio
// derivado de datos -- son las bandas de estado a mostrar, ya definidas por el enunciado).
const ESTADO_CONFIG: Record<EstadoMeta, { label: string; barColor: string; badgeVariant: 'danger' | 'warning' | 'info' | 'success' }> = {
  riesgo:    { label: 'Riesgo',         barColor: 'bg-danger',   badgeVariant: 'danger' },
  cerca:     { label: 'Cerca',          barColor: 'bg-warning', badgeVariant: 'warning' },
  proxima:   { label: 'Meta próxima',   barColor: 'bg-info',  badgeVariant: 'info' },
  alcanzada: { label: 'Meta alcanzada', barColor: 'bg-success', badgeVariant: 'success' },
};

const estadoDeMeta = (cumplimientoPct: number): EstadoMeta => {
  if (cumplimientoPct >= 100) return 'alcanzada';
  if (cumplimientoPct >= 90) return 'proxima';
  if (cumplimientoPct >= 80) return 'cerca';
  return 'riesgo';
};

export const VendorGoalDashboard = () => {
  const { data, loading, error } = useMyGoalTracking();
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
        <Badge variant="info" dot>Datos en vivo — EDW</Badge>
      </div>

      {error && <div className="card p-4 text-danger text-sm">{error}</div>}

      {/* Meta mensual */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 stagger-children">
        {loading ? (
          <><KpiCardSkeleton /><KpiCardSkeleton /><KpiCardSkeleton /><KpiCardSkeleton /></>
        ) : (
          <>
            <KpiCard title="Meta Asignada" value={fmt(metaMensual)} icon={Target} trend="neutral" />
            <KpiCard title="Ventas Actuales" value={fmt(ventasActuales)} icon={TrendingUp} trend={cumplimientoPct >= 90 ? 'up' : 'down'} />
            <KpiCard title="Cumplimiento" value={pct(cumplimientoPct)} icon={Wallet} trend={cumplimientoPct >= 100 ? 'up' : 'neutral'} />
            <KpiCard title="Restante" value={fmt(restante)} icon={Target} trend="neutral" />
          </>
        )}
      </div>

      {/* Medidor de progreso -- D3, tramos = umbrales reales de comisión (commission_engine.py) */}
      <ChartCard title="Progreso hacia la meta" badge={{ label: 'Live', variant: 'live' }} height="h-auto" loading={loading}>
        <div className="flex flex-col items-center gap-1 py-2">
          <GoalProgressGauge pctCumplimiento={cumplimientoPct} />
          <div className="flex flex-col items-center gap-2 -mt-2">
            <span className="font-mono text-3xl font-semibold text-slate-100">{pct(cumplimientoPct)}</span>
            <Badge variant={estado.badgeVariant}>{estado.label}</Badge>
          </div>
          {comision.data?.mensaje_alerta && (
            <p className={`text-sm mt-2 text-center ${comision.data.en_alerta_cierre ? 'text-warning' : 'text-success'}`}>
              {comision.data.mensaje_alerta}
            </p>
          )}
        </div>
      </ChartCard>

      {/* Meta sugerida (próximo período) -- 100% estadística, sin modelo ML (goals_rf
          decomisionado). El "Pronóstico de cierre" (sales_rf) se retiró por completo,
          auditoría 49. */}
      <ChartCard title="Meta sugerida (próximo período)" badge={{ label: 'Estadística', variant: 'hist' }} loading={metaSugerida.loading} error={metaSugerida.error ?? undefined} height="h-[220px]">
        <div className="flex flex-col items-center justify-center h-full gap-2">
          <Target size={20} className="text-info" aria-hidden="true" />
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
      </ChartCard>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Comisión -- única y variable (docs/features/plan_motor_metas_v3_y_comisiones_
            unificadas.md, Fase 1, R-1): ya no hay un esquema plano paralelo que comparar. */}
        <ChartCard
          title="Comisión"
          badge={{ label: comision.data?.nivel ?? '—', variant: 'live' }}
          loading={comision.loading}
          error={comision.error ?? undefined}
          height="h-[220px]"
        >
          <div className="grid grid-cols-2 gap-4 h-full items-center">
            <div className="flex flex-col items-center text-center gap-1">
              <Wallet size={20} className="text-success" aria-hidden="true" />
              <span className="font-mono text-2xl font-semibold text-slate-100">
                {comision.data ? fmtMoney(comision.data.comision_devengada) : '—'}
              </span>
              <span className="text-xs text-slate-500">Comisión devengada</span>
            </div>
            <div className="flex flex-col items-center text-center gap-1">
              <TrendingUp size={20} className="text-info" aria-hidden="true" />
              <span className="font-mono text-2xl font-semibold text-slate-100">
                {comision.data ? `${comision.data.tasa_aplicada_pct.toFixed(2)}%` : '—'}
              </span>
              <span className="text-xs text-slate-500">Tasa efectiva</span>
            </div>
            {comision.data && comision.data.bono_aplicado > 0 && (
              <div className="col-span-2 flex items-center justify-center gap-2 text-sm text-warning">
                <Gift size={14} aria-hidden="true" />
                <span>Incluye bonos (cross-sell, cliente nuevo, cobranza sana): {fmtMoney(comision.data.bono_aplicado)}</span>
              </div>
            )}
            {comision.data && (
              <p className="col-span-2 text-xs text-slate-500 text-center">
                Venta Neta {fmtMoney(comision.data.venta_real)} de meta {fmtMoney(comision.data.monto_meta)}
                {comision.data.comision_devengada === 0 && comision.data.pct_cumplimiento < 100 && (
                  <span className="block text-danger mt-1">
                    No alcanzaste el umbral mínimo de cumplimiento este período -- sin comisión.
                  </span>
                )}
              </p>
            )}
            {comision.data?.desglose_variable && (
              <details className="col-span-2 text-xs text-slate-400">
                <summary className="cursor-pointer text-center text-primary hover:text-primary">
                  Ver cómo se calculó
                </summary>
                <ul className="mt-2 space-y-1 font-mono">
                  <li className="flex justify-between"><span>Base por línea (categoría/margen)</span><span>{fmtMoney(comision.data.desglose_variable.comision_base)}</span></li>
                  <li className="flex justify-between"><span>× Tipo de vendedor</span><span>{fmtMoney(comision.data.desglose_variable.comision_post_tipo)}</span></li>
                  <li className="flex justify-between"><span>× Cumplimiento ({comision.data.desglose_variable.multiplicador_cumplimiento.toFixed(2)}×)</span><span>{fmtMoney(comision.data.desglose_variable.comision_post_cumplimiento)}</span></li>
                  <li className="flex justify-between"><span>− Devoluciones estimadas</span><span>{fmtMoney(comision.data.desglose_variable.devoluciones_estimadas)}</span></li>
                  <li className="flex justify-between"><span>+ Bonos (venta cruzada, cliente nuevo, cobranza)</span><span>{fmtMoney(comision.data.desglose_variable.bonos_total)}</span></li>
                  <li className="flex justify-between border-t border-slate-800 pt-1 text-primary font-semibold"><span>Total</span><span>{fmtMoney(comision.data.desglose_variable.comision_final)}</span></li>
                </ul>
              </details>
            )}
          </div>
        </ChartCard>

        {/* Recomendaciones de productos -- reglas de asociación */}
        <ChartCard
          title="Productos recomendados para cerrar tu meta"
          badge={{ label: 'Reglas Asociación', variant: 'ml' }}
          loading={recomendaciones.loading}
          error={recomendaciones.error ?? undefined}
          empty={recomendaciones.data.length === 0}
          emptyDescription="Sin recomendaciones disponibles todavía."
          height="h-[220px]"
        >
          <ul className="space-y-2 overflow-auto max-h-[170px]">
            {recomendaciones.data.map((r, i) => (
              <li key={i} className="flex justify-between items-center py-2 border-b border-slate-800 last:border-0">
                <div className="flex items-center gap-1.5">
                  <Sparkles size={13} className="text-warning" aria-hidden="true" />
                  <p className="text-sm font-medium text-slate-200 font-mono">{r.producto_cod}</p>
                </div>
                <Badge variant="info">lift {r.score_afinidad.toFixed(1)}</Badge>
              </li>
            ))}
          </ul>
        </ChartCard>
      </div>

      {/* Facturas post-meta -- solo se muestra al alcanzar el 100% de la meta */}
      {metaAlcanzada && (
        <ChartCard
          title="Facturas post-meta"
          badge={{ label: 'Live', variant: 'live' }}
          loading={postMeta.loading}
          error={postMeta.error ?? undefined}
          height="h-[240px]"
        >
          <div className="flex flex-col h-full gap-3">
            <div className="flex items-center justify-center gap-2">
              <Trophy size={20} className="text-warning" aria-hidden="true" />
              <Badge variant="success">¡Meta alcanzada este período!</Badge>
            </div>
            {postMeta.data.length === 0 ? (
              <p className="text-slate-500 text-sm text-center mt-4">Aún no hay facturas registradas después de cruzar la meta.</p>
            ) : (
              <ul className="space-y-1.5 overflow-auto flex-1">
                {postMeta.data.map((f) => (
                  <li key={f.num_factura} className="flex justify-between items-center py-1.5 border-b border-slate-800 last:border-0">
                    <div className="flex items-center gap-1.5">
                      <Receipt size={13} className="text-info" />
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
