import { useState } from 'react';
import {
  ResponsiveContainer, ComposedChart, Line, Bar, CartesianGrid, XAxis, YAxis, Tooltip,
} from 'recharts';
import { Target, Wallet, Trophy, TrendingUp, Package, AlertTriangle, Users } from 'lucide-react';
import { useMiNegocio, useChurnRisk, useRecommendations, useCustomerSegment } from '../hooks/ventas';
import { useSearchClientes } from '../hooks/crossSelling';
import { KpiCard, KpiCardSkeleton } from '../components/ui/KpiCard';
import { ChartCard } from '../components/ui/ChartCard';
import { Badge } from '../components/ui/Badge';
import { ErrorState } from '../components/ui/ErrorState';
import { EmptyState } from '../components/ui/EmptyState';
import { Autocomplete } from '../components/ui/Autocomplete';
import { PriorityCard } from '../components/rutaInteligente/PriorityCard';
import { UpcomingActions } from '../components/rutaInteligente/UpcomingActions';
import { ClientDetailDrawer } from '../components/rutaInteligente/ClientDetailDrawer';
import { ChartTooltip } from '../components/ui/ChartTooltip';
import { chartTheme, axisTick } from '../utils/chartTheme';
import { fmtMoney, pct } from '../utils/format';
import type { ClienteBusqueda } from '../types/crossSelling';
import type { ClienteRuta } from '../types/cartera360';

const NOMBRE_MES_CORTO = [
  'Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic',
];

const segmentVariant = (nombre: string): 'success' | 'info' | 'warning' | 'danger' => {
  const n = nombre.toLowerCase();
  if (n.includes('vip') || n.includes('leal')) return 'success';
  if (n.includes('nuevo')) return 'info';
  if (n.includes('riesgo') || n.includes('inactiv')) return 'danger';
  return 'warning';
};

/** Dashboard "Mi Negocio" del vendedor (auditoría 43, Fase 5,
 * docs/auditoria/43_correcciones_sesion_ventas_y_datos.md, H43-16): antes esta página
 * era efectivamente un formulario de búsqueda -- 3 de sus 4 paneles nunca se veían salvo
 * que el vendedor escribiera un `cliente_id` exacto de memoria, sin autocompletar.
 * Ahora consume `GET /analytics/ventas/mi-negocio` (una sola llamada agregadora, sin
 * modelos ML nuevos) y organiza la información en capas: scoreboard del mes, prioridades
 * de hoy + agenda, tendencia y desempeño, y análisis puntual de un cliente. */
export const DashboardVentas = () => {
  const negocio = useMiNegocio();
  const [clienteAbierto, setClienteAbierto] = useState<ClienteRuta | null>(null);

  const [busquedaCliente, setBusquedaCliente] = useState('');
  const [clienteAnalisis, setClienteAnalisis] = useState<ClienteBusqueda | null>(null);
  const clientesEncontrados = useSearchClientes(busquedaCliente);
  const churn = useChurnRisk();
  const recs = useRecommendations();
  const seg = useCustomerSegment();

  const seleccionarClienteAnalisis = (c: ClienteBusqueda) => {
    setClienteAnalisis(c);
    churn.execute(c.cliente_id);
    recs.execute(c.cliente_id);
    seg.execute(c.cliente_id);
  };

  const abrirClienteDesdeLista = (lista: ClienteRuta[], clienteId: string) => {
    const cliente = lista.find((c) => c.cliente_id === clienteId);
    if (cliente) setClienteAbierto(cliente);
  };

  const data = negocio.data;
  const evolucion = (data?.evolucion_mensual ?? []).map((p) => ({
    label: `${NOMBRE_MES_CORTO[p.mes - 1]} ${String(p.anio).slice(2)}`,
    venta_real: p.venta_real,
    meta: p.meta,
  }));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap justify-between items-center gap-3 animate-fade-in">
        <div>
          <h1 className="text-3xl font-display font-semibold text-slate-100">Mi Negocio</h1>
          <p className="text-sm text-slate-500 mt-0.5">Tu cuota, tu cartera y qué hacer hoy para vender más mañana</p>
        </div>
        <Badge variant="info" dot>ML Activo — churn_rf · segmentation · association</Badge>
      </div>

      {negocio.error && (
        <div className="card p-6">
          <ErrorState message={negocio.error} onRetry={negocio.refetch} />
        </div>
      )}

      {/* Fila 1 — Scoreboard del mes */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 stagger-children">
        {negocio.loading ? (
          <><KpiCardSkeleton /><KpiCardSkeleton /><KpiCardSkeleton /><KpiCardSkeleton /></>
        ) : data && (
          <>
            <KpiCard
              title="Cuota del mes"
              value={fmtMoney(data.cuota.venta_actual)}
              subValue={`${pct(data.cuota.pct_cumplimiento)} de ${fmtMoney(data.cuota.meta_mensual)}`}
              icon={Target}
              trend={data.cuota.pct_cumplimiento >= 100 ? 'up' : data.cuota.pct_cumplimiento >= 80 ? 'neutral' : 'down'}
              sparkline={evolucion.map((p) => p.venta_real)}
            />
            <KpiCard
              title="Meta de hoy"
              value={data.meta_diaria.objetivo_diario != null ? fmtMoney(data.meta_diaria.objetivo_diario) : '—'}
              subValue={
                data.meta_diaria.objetivo_diario != null
                  ? `Llevas ${fmtMoney(data.meta_diaria.venta_hoy)} hoy`
                  : 'Sin meta generada este mes'
              }
              icon={TrendingUp}
              trend={
                data.meta_diaria.objetivo_diario
                  ? (data.meta_diaria.venta_hoy >= data.meta_diaria.objetivo_diario ? 'up' : 'down')
                  : 'neutral'
              }
            />
            <KpiCard
              title="Próximo pago de comisión"
              value={fmtMoney(data.comision.comision_variable ?? data.comision.comision_devengada)}
              subValue={`Tasa ${data.comision.tasa_aplicada_pct.toFixed(2)}% · ${data.comision.dias_restantes_mes} días restantes`}
              icon={Wallet}
              trend="neutral"
            />
            <KpiCard
              title="Ranking del mes"
              value={data.ranking ? `#${data.ranking.posicion} de ${data.ranking.total}` : '—'}
              subValue={data.ranking ? 'Entre todos los vendedores activos' : 'Sin ventas registradas este mes'}
              icon={Trophy}
              trend="neutral"
            />
          </>
        )}
      </div>

      {/* Fila 2 — Prioridades de hoy + agenda */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card p-6">
          <h3 className="font-sans font-semibold text-slate-200 mb-1 flex items-center gap-2">
            <AlertTriangle size={16} className="text-warning" /> Clientes en riesgo
          </h3>
          <p className="text-xs text-slate-500 mb-4">Riesgo de fuga real (modelo de churn), no una regla arbitraria</p>
          {negocio.loading ? (
            <div className="space-y-3">{[1, 2, 3].map((i) => <div key={i} className="skeleton h-20 rounded-lg" />)}</div>
          ) : data && data.clientes_en_riesgo.length > 0 ? (
            <div className="space-y-3">
              {data.clientes_en_riesgo.map((c) => (
                <PriorityCard
                  key={c.cliente_id} cliente={c} valorMaximo={data.clientes_en_riesgo[0].valor_historico}
                  onClick={() => abrirClienteDesdeLista(data.clientes_en_riesgo, c.cliente_id)}
                />
              ))}
            </div>
          ) : (
            <EmptyState icon={Users} title="Sin clientes en riesgo crítico hoy" description="Buena señal: tu cartera priorizada no muestra riesgo alto en este momento." />
          )}
        </div>

        <div className="card p-6">
          <h3 className="font-sans font-semibold text-slate-200 mb-4">Próximas acciones</h3>
          <UpcomingActions onSelect={(clienteId) => data && abrirClienteDesdeLista([...data.clientes_en_riesgo, ...data.pipeline], clienteId)} />
        </div>
      </div>

      {/* Fila 3 — Tendencia y desempeño */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <ChartCard
          title="Evolución mensual (real vs. meta)"
          badge={{ label: 'EDW', variant: 'hist' }}
          className="lg:col-span-2"
          loading={negocio.loading}
          error={negocio.error ?? undefined}
          onRetry={negocio.refetch}
          empty={!negocio.loading && evolucion.length === 0}
          emptyDescription="Sin historial de ventas suficiente todavía."
          height="h-[280px]"
        >
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={evolucion} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} vertical={false} />
              <XAxis dataKey="label" tick={axisTick} axisLine={false} tickLine={false} />
              <YAxis tick={axisTick} axisLine={false} tickLine={false} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
              <Tooltip
                content={({ active, payload, label }) => {
                  if (!active || !payload?.length) return null;
                  return (
                    <ChartTooltip
                      title={label}
                      rows={payload.map((row) => ({
                        label: row.name === 'venta_real' ? 'Venta real' : 'Meta',
                        value: fmtMoney(Number(row.value ?? 0)),
                        color: row.color,
                      }))}
                    />
                  );
                }}
              />
              <Bar dataKey="venta_real" name="venta_real" fill={chartTheme.live} radius={[4, 4, 0, 0]} />
              <Line dataKey="meta" name="meta" stroke={chartTheme.ml} strokeWidth={2} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="Productos más vendidos"
          badge={{ label: 'EDW', variant: 'hist' }}
          loading={negocio.loading}
          empty={!negocio.loading && (data?.top_productos.length ?? 0) === 0}
          emptyDescription="Sin ventas en los últimos 3 meses."
          height="h-[280px]"
        >
          <ul className="space-y-2 overflow-auto h-full pr-1">
            {data?.top_productos.map((p) => (
              <li key={p.codart} className="flex items-center justify-between gap-2 py-2 border-b border-slate-800 last:border-0">
                <div className="min-w-0">
                  <p className="text-sm text-slate-200 truncate">{p.nombre}</p>
                  <p className="text-xs text-slate-500 font-mono">{p.codart}</p>
                </div>
                <span className="text-xs font-mono text-slate-400 shrink-0">{fmtMoney(p.venta)}</span>
              </li>
            ))}
          </ul>
        </ChartCard>
      </div>

      {/* Análisis individual de cliente */}
      <div className="card p-6 animate-fade-in-up">
        <h3 className="font-sans font-semibold text-slate-200 mb-1 flex items-center gap-2">
          <Package size={16} /> Análisis individual de cliente
        </h3>
        <p className="text-xs text-slate-500 mb-4">Busca por cédula/RUC o nombre — sin necesidad de recordar el código exacto</p>
        {clienteAnalisis ? (
          <Badge variant="info" className="pr-1 mb-4">
            {clienteAnalisis.nombre} <span className="font-mono text-xs opacity-70 ml-1">{clienteAnalisis.cliente_id}</span>
            <button onClick={() => setClienteAnalisis(null)} className="ml-1 hover:text-danger">×</button>
          </Badge>
        ) : (
          <Autocomplete<ClienteBusqueda>
            placeholder="Busca por cédula/RUC o nombre del cliente…"
            label="Cliente a analizar"
            loading={clientesEncontrados.loading}
            options={clientesEncontrados.data}
            onQueryChange={setBusquedaCliente}
            getKey={(c) => c.cliente_id}
            onSelect={seleccionarClienteAnalisis}
            renderOption={(c) => (
              <span className="flex justify-between">
                <span className="truncate">{c.nombre}</span>
                <span className="text-slate-500 font-mono text-xs ml-2 shrink-0">{c.cliente_id}</span>
              </span>
            )}
          />
        )}

        {clienteAnalisis && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mt-4 animate-fade-in">
            <ChartCard
              title="Segmento RFM" badge={{ label: 'K-Means', variant: 'ml' }}
              loading={seg.loading} error={seg.error ?? undefined} onRetry={() => seg.execute(clienteAnalisis.cliente_id)}
              empty={!seg.loading && !seg.error && !seg.data}
              emptyDescription="Sin datos aún."
            >
              {seg.data && (
                <div className="flex flex-col items-center justify-center h-full gap-4">
                  <Badge variant={segmentVariant(seg.data.nombre_segmento)} className="text-base px-4 py-2">
                    {seg.data.nombre_segmento}
                  </Badge>
                  <p className="text-xs text-slate-500 font-mono">Cluster #{seg.data.segmento}</p>
                </div>
              )}
            </ChartCard>

            <ChartCard
              title="Riesgo de Abandono (Churn)" badge={{ label: 'Random Forest', variant: 'ml' }}
              loading={churn.loading} error={churn.error ?? undefined} onRetry={() => churn.execute(clienteAnalisis.cliente_id)}
              empty={!churn.loading && !churn.error && !churn.data}
              emptyDescription="Sin datos aún."
            >
              {churn.data && (
                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <span className="font-mono text-3xl font-semibold text-slate-100">
                      {(churn.data.probabilidad_abandono).toFixed(1)}%
                    </span>
                    <Badge variant={churn.data.riesgo_alto ? 'danger' : 'success'}>
                      {churn.data.riesgo_alto ? 'Riesgo Alto' : 'Riesgo Bajo'}
                    </Badge>
                  </div>
                  <div className="h-3 bg-slate-800 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${churn.data.riesgo_alto ? 'bg-danger' : 'bg-success'}`}
                      style={{ width: `${Math.min(100, churn.data.probabilidad_abandono)}%` }}
                    />
                  </div>
                </div>
              )}
            </ChartCard>

            <ChartCard
              title="Recomendaciones de Venta Cruzada" badge={{ label: 'Reglas Asociación', variant: 'ml' }}
              loading={recs.loading} error={recs.error ?? undefined} onRetry={() => recs.execute(clienteAnalisis.cliente_id)}
              empty={!recs.loading && !recs.error && !recs.data?.recomendaciones?.length}
              emptyDescription="Sin recomendaciones disponibles."
            >
              {recs.data?.recomendaciones?.length ? (
                <ul className="space-y-2 overflow-auto max-h-[220px]">
                  {recs.data.recomendaciones.map((r, i) => (
                    <li key={i} className="flex justify-between items-center py-2 border-b border-slate-800 last:border-0">
                      <span className="text-sm text-slate-200 truncate">{r.nombre ?? r.producto_cod}</span>
                      {r.confianza != null && <Badge variant="info">{(r.confianza * 100).toFixed(0)}%</Badge>}
                    </li>
                  ))}
                </ul>
              ) : null}
            </ChartCard>
          </div>
        )}
      </div>

      <ClientDetailDrawer cliente={clienteAbierto} onClose={() => setClienteAbierto(null)} />
    </div>
  );
};
