import { useState } from 'react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar,
  PieChart, Pie, Cell, Legend
} from 'recharts';
import { DollarSign, TrendingUp, ShoppingBag, Target, Filter, CheckCircle2, FileSpreadsheet, Printer } from 'lucide-react';
import {
  useGerenciaKPIs, useSalesPrediction, useRevenueByCategory, useCategories, useVendedores, useAlmacenes,
  useCumplimientoMeta,
} from '../hooks/gerencia';
import { descargarReporteDashboardExcel } from '../services/gerencia';
import { KpiCard, KpiCardSkeleton } from '../components/ui/KpiCard';
import { ChartCard } from '../components/ui/ChartCard';
import { AlertBadge } from '../components/ui/AlertBadge';
import { Select } from '../components/ui/Select';
import { Button } from '../components/ui/Button';
import { ChartTooltip } from '../components/ui/ChartTooltip';
import { ErrorState } from '../components/ui/ErrorState';
import { CrossSellKpiPanel } from '../components/crossSelling/CrossSellKpiPanel';
import { useToast } from '../store/toastStore';
import { fmt, fmtMoney, formatEjeFecha, pct } from '../utils/format';
import { chartTheme, colorByIndex, axisTick } from '../utils/chartTheme';

export const DashboardGerencia = () => {
  const [filters, setFilters] = useState({
    start_date: '',
    end_date: '',
    categoria: '',
    vendedor: '',
    almacen: '',
  });
  const [granularidad, setGranularidad] = useState<'semana' | 'mes'>('semana');
  const [descargando, setDescargando] = useState(false);
  const toast = useToast();

  const kpi  = useGerenciaKPIs(filters);
  // Fase 2 Gerencia (docs/features/plan_correcciones_pendientes.md §3): KPI de
  // cumplimiento vs metas -- período actual (mes calendario en curso), reutiliza
  // public.metas_comerciales_operativas, sin ML (regla de negocio 10).
  const hoy = new Date();
  const cumplimiento = useCumplimientoMeta(hoy.getFullYear(), hoy.getMonth() + 1);
  const pred = useSalesPrediction({ granularidad, vendedor: filters.vendedor, almacen: filters.almacen });
  const revCat = useRevenueByCategory(filters);
  const { data: categoriasLista } = useCategories();
  const { data: vendedoresLista } = useVendedores();
  const { data: almacenesLista } = useAlmacenes();

  // Switch between Branch logic or Seller logic for the Donut Chart based on active branch filter
  // Updated: even when "Todas las Sucursales" is selected, show "Distribución por Vendedor" to align with goals and commissions
  const donutData = kpi.data?.ventas_por_vendedor
    ? Object.entries(kpi.data.ventas_por_vendedor).map(([name, value]) => ({ name, value }))
    : [];

  const donutTitle = "Distribución por Vendedor";

  // Fase 2 Gerencia (docs/features/plan_correcciones_pendientes.md §3): comparativa vs.
  // período anterior -- null cuando no hay start_date/end_date explícitos (sin subValue).
  const tendencia = (pctChange: number | null | undefined) => {
    if (pctChange == null) return { subValue: undefined, trend: 'neutral' as const };
    return {
      subValue: `${pctChange > 0 ? '+' : ''}${pctChange.toFixed(1)}% vs período anterior`,
      trend: pctChange > 0 ? ('up' as const) : pctChange < 0 ? ('down' as const) : ('neutral' as const),
    };
  };

  // Fase 2 Gerencia (docs/features/plan_correcciones_pendientes.md §3): export del
  // dashboard -- Excel real (backend, reutiliza warehouse_export.py) + PDF vía
  // impresión del navegador (mismo patrón que BodegaReportes.tsx, sin librería nueva).
  const exportarExcel = async () => {
    setDescargando(true);
    try {
      await descargarReporteDashboardExcel(filters);
      toast('Reporte Excel descargado correctamente.', 'success');
    } catch {
      toast('No se pudo descargar el reporte Excel. Intenta nuevamente.', 'error');
    } finally {
      setDescargando(false);
    }
  };

  const salud = kpi.data?.roi_estimado;
  const saludVariant = salud
    ? salud >= 20 ? 'success' : salud >= 10 ? 'warning' : 'critical'
    : 'neutral';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap justify-between items-center gap-3 animate-fade-in print:hidden">
        <div>
          <h1 className="text-3xl font-display font-semibold text-slate-100">Visión Ejecutiva</h1>
          <p className="text-sm text-slate-500 mt-0.5">Datos consolidados del Data Warehouse · Modo tiempo real</p>
        </div>
        <div className="flex items-center gap-2">
          <AlertBadge variant="info" dot>
            Modelo {pred.data?.metricas.algoritmo ?? 'ML'} activo
          </AlertBadge>
          <Button
            variant="success" size="sm" onClick={exportarExcel} disabled={kpi.loading}
            loading={descargando} icon={!descargando ? <FileSpreadsheet size={14} aria-hidden="true" /> : undefined}
            aria-label="Exportar reporte del dashboard a Excel"
          >
            {descargando ? 'Generando…' : 'Excel'}
          </Button>
          <Button
            variant="primary" size="sm" onClick={() => window.print()} disabled={kpi.loading}
            icon={<Printer size={14} aria-hidden="true" />} aria-label="Imprimir o exportar a PDF"
          >
            PDF
          </Button>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="p-4 bg-slate-800/50 rounded-lg border border-slate-700/50 flex flex-wrap gap-4 items-center print:hidden">
        <div className="flex items-center gap-2 text-slate-400">
          <Filter className="w-4 h-4" />
          <span className="text-sm font-medium">Filtros:</span>
        </div>

        <input
          type="date"
          value={filters.start_date}
          onChange={(e) => setFilters(f => ({ ...f, start_date: e.target.value }))}
          className="bg-slate-900 border border-slate-700 text-sm text-slate-300 rounded p-1.5 focus-ring"
          title="Fecha de Inicio"
        />
        <span className="text-slate-500">-</span>
        <input
          type="date"
          value={filters.end_date}
          onChange={(e) => setFilters(f => ({ ...f, end_date: e.target.value }))}
          className="bg-slate-900 border border-slate-700 text-sm text-slate-300 rounded p-1.5 focus-ring"
          title="Fecha de Fin"
        />

        <Select
          aria-label="Filtrar por vendedor"
          value={filters.vendedor}
          onChange={(e) => setFilters(f => ({ ...f, vendedor: e.target.value }))}
          className="min-w-[150px]"
        >
          <option value="">Todos los Vendedores</option>
          {vendedoresLista?.map(vend => (
            <option key={vend} value={vend}>{vend}</option>
          ))}
        </Select>

        <Select
          aria-label="Filtrar por categoría"
          value={filters.categoria}
          onChange={(e) => setFilters(f => ({ ...f, categoria: e.target.value }))}
          className="min-w-[150px]"
        >
          <option value="">Todas las Categorías</option>
          {categoriasLista?.map(cat => (
            <option key={cat} value={cat}>{cat}</option>
          ))}
        </Select>

        <Select
          aria-label="Filtrar por almacén"
          value={filters.almacen}
          onChange={(e) => setFilters(f => ({ ...f, almacen: e.target.value }))}
          className="min-w-[150px]"
        >
          <option value="">Todos los Almacenes</option>
          {almacenesLista?.map(alm => (
            <option key={alm} value={alm}>{alm}</option>
          ))}
        </Select>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-4 stagger-children">
        {kpi.loading ? (
          <>
            <KpiCardSkeleton />
            <KpiCardSkeleton />
            <KpiCardSkeleton />
            <KpiCardSkeleton />
            <KpiCardSkeleton />
          </>
        ) : kpi.error ? (
          <div className="col-span-5">
            <ErrorState message={`Error al cargar KPIs: ${kpi.error}`} onRetry={kpi.refetch} />
          </div>
        ) : (
          <>
            <KpiCard
              title="Ingresos Totales (ventas-devoluciones)"
              value={kpi.data ? fmtMoney(kpi.data.ingresos_totales) : '—'}
              icon={DollarSign}
              {...tendencia(kpi.data?.ingresos_totales_tendencia_pct)}
            />
            <KpiCard
              title="Margen de Utilidad"
              value={kpi.data ? pct(kpi.data.margen_utilidad_neta) : '—'}
              icon={TrendingUp}
              {...tendencia(kpi.data?.margen_utilidad_neta_tendencia_pct)}
            />
            <KpiCard
              title="FACTURA Promedio"
              value={kpi.data ? fmt(kpi.data.ticket_promedio) : '—'}
              icon={ShoppingBag}
              {...tendencia(kpi.data?.ticket_promedio_tendencia_pct)}
            />
            <KpiCard
              title="Proyección ROI"
              value={kpi.data ? pct(kpi.data.roi_estimado) : '—'}
              icon={Target}
              trend={
                kpi.data?.roi_estimado_tendencia_pct != null
                  ? tendencia(kpi.data.roi_estimado_tendencia_pct).trend
                  : saludVariant === 'success' ? 'up' : saludVariant === 'critical' ? 'down' : 'neutral'
              }
              subValue={tendencia(kpi.data?.roi_estimado_tendencia_pct).subValue}
            />
            <KpiCard
              title="Cumplimiento vs Meta (mes actual)"
              value={cumplimiento.data ? pct(cumplimiento.data.pct_cumplimiento) : '—'}
              icon={CheckCircle2}
              trend={
                cumplimiento.data
                  ? cumplimiento.data.pct_cumplimiento >= 100 ? 'up'
                    : cumplimiento.data.pct_cumplimiento >= 70 ? 'neutral' : 'down'
                  : 'neutral'
              }
            />
          </>
        )}
      </div>
      {cumplimiento.data && cumplimiento.data.vendedores_con_meta_aprobada === 0 && (
        <p className="text-xs text-slate-500 -mt-3">
          Sin metas aprobadas para el mes en curso -- el % de cumplimiento no tiene base de comparación todavía.
        </p>
      )}

      {/* Panel Ejecutivo de Predicción */}
      {pred.data && !pred.loading && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 animate-fade-in">
          <div className="col-span-1 md:col-span-2">
            <ChartCard
              title="Histórico y Predicción de Ventas (ML)"
              badge={{ label: pred.data.metricas.algoritmo ?? 'ML', variant: 'ml' }}
              actions={
                <div className="flex items-center gap-1 bg-slate-800/70 border border-slate-700/50 rounded-full p-0.5">
                  {(['semana', 'mes'] as const).map((g) => (
                    <button
                      key={g}
                      type="button"
                      onClick={() => setGranularidad(g)}
                      className={`px-3 py-1 text-xs font-medium rounded-full transition-colors focus-ring ${
                        granularidad === g ? 'bg-primary/20 text-primary' : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      {g === 'semana' ? 'Semanas' : 'Meses'}
                    </button>
                  ))}
                </div>
              }
            >
              {/* G-1 (docs/auditoria/33_actualizacion_modulo_gerencia.md, H1): el modelo
                  sales_rf no fue entrenado con la columna categoría y usa una ventana
                  continua de historial (no un rango arbitrario), así que "Fecha" y
                  "Categoría" de la barra de filtros no afectan esta predicción -- solo
                  a los KPIs e ingresos por categoría de abajo. Aclarado en vez de fingir
                  que el forecast los respeta. */}
              <p className="text-xs text-slate-500 mb-3 -mt-2">
                Este forecast respeta los filtros de <span className="text-slate-400 font-medium">vendedor</span> y{' '}
                <span className="text-slate-400 font-medium">almacén</span>; el modelo no soporta filtrar por fecha ni categoría
                (usa siempre el historial continuo completo).
              </p>
              <ResponsiveContainer width="100%" height={380}>
                <AreaChart
                  data={pred.data.historial_y_prediccion}
                  margin={{ top: 20, right: 30, left: 0, bottom: 0 }}
                >
                  <defs>
                    <linearGradient id="gradHist" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={chartTheme.palette[0]} stopOpacity={0.3} />
                      <stop offset="95%" stopColor={chartTheme.palette[0]} stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="gradPred" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={chartTheme.live} stopOpacity={0.4} />
                      <stop offset="95%" stopColor={chartTheme.live} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} vertical={false} />
                  <XAxis
                    dataKey="fecha"
                    stroke={chartTheme.grid}
                    tick={axisTick}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(v) => formatEjeFecha(v, granularidad)}
                    minTickGap={30}
                  />
                  <YAxis
                    stroke={chartTheme.grid}
                    tick={axisTick}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(v) => `$${v / 1000}k`}
                    width={55}
                  />
                  <Tooltip
                    content={({ active, payload, label }) => {
                      if (!active || !payload?.length) return null;
                      const rows = payload
                        .filter((p) => p.value != null)
                        .map((p) => ({
                          label: p.name === 'monto_real' ? 'Real' : p.name === 'monto_predicho' ? 'Predicho' : String(p.name),
                          value: `$${Number(p.value).toLocaleString(undefined, { minimumFractionDigits: 2 })}`,
                          color: p.color,
                        }));
                      return <ChartTooltip title={formatEjeFecha(String(label), granularidad)} rows={rows} />;
                    }}
                  />
                  <Legend verticalAlign="top" height={36} wrapperStyle={{ fontSize: '12px', color: chartTheme.axisLabel }} />

                  {/* Historic Area */}
                  <Area
                    connectNulls={true}
                    type="monotone"
                    dataKey="monto_real"
                    stroke={chartTheme.palette[0]}
                    strokeWidth={2.5}
                    fill="url(#gradHist)"
                    name="Histórico Real"
                    dot={false}
                    activeDot={{ r: 4, fill: chartTheme.palette[0], stroke: chartTheme.cardBg, strokeWidth: 2 }}
                  />

                  {/* Prediction Area */}
                  <Area
                  connectNulls={true}
                    type="monotone"
                    dataKey="monto_predicho"
                    stroke={chartTheme.live}
                    strokeWidth={2.5}
                    strokeDasharray="5 5"
                    fill="url(#gradPred)"
                    name="Predicción Futura"
                    dot={false}
                    activeDot={{ r: 6, fill: chartTheme.live, stroke: chartTheme.cardBg, strokeWidth: 2 }}
                  />

                  {/* Confidence Interval Lines */}
                  {pred.data.historial_y_prediccion.some(d => d.intervalo_superior) && (
                    <>
                      <Area type="monotone" dataKey="intervalo_superior" stroke={chartTheme.live} strokeWidth={1} strokeDasharray="3 3" fill="none" name="Límite Superior (95%)" dot={false} />
                      <Area type="monotone" dataKey="intervalo_inferior" stroke={chartTheme.live} strokeWidth={1} strokeDasharray="3 3" fill="none" name="Límite Inferior (95%)" dot={false} />
                    </>
                  )}
                </AreaChart>
              </ResponsiveContainer>
            </ChartCard>
          </div>

          <div className="col-span-1 space-y-4 flex flex-col">
            {/* Insights panel */}
            <div className="card p-5 border border-slate-700/50 bg-slate-800/40 rounded-xl flex-grow">
              <h3 className="text-lg font-medium tracking-tight text-slate-100 flex items-center gap-2 mb-4">
                <Target className="w-5 h-5 text-primary" /> Inteligencia Comercial
              </h3>
              <ul className="space-y-4 text-sm text-slate-300">
                {pred.data.insights.map((insight, idx) => (
                  <li key={idx} className="flex gap-3">
                    <span className="flex-shrink-0 w-1.5 h-1.5 mt-2 rounded-full bg-primary"></span>
                    <span className="leading-snug">{insight}</span>
                  </li>
                ))}
              </ul>

              {/* metricas llega vacía (todo null) cuando la serie filtrada no tiene datos:
                  el backend degrada con gracia en vez de responder 500 (doc 22). */}
              <div className="mt-6 pt-6 border-t border-slate-700/50 grid grid-cols-2 gap-4">
                <div>
                  <div className="text-xs text-slate-500 mb-1">Crecimiento Est.</div>
                  <div className={`text-lg font-semibold ${(pred.data.metricas.crecimiento_esperado ?? 0) > 0 ? 'text-success' : 'text-danger'}`}>
                    {pred.data.metricas.crecimiento_esperado != null
                      ? `${pred.data.metricas.crecimiento_esperado > 0 ? '+' : ''}${pred.data.metricas.crecimiento_esperado.toFixed(1)}%`
                      : '—'}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-slate-500 mb-1">
                    Proyección ({pred.data.periodos_proyectados} {granularidad === 'semana' ? 'sem' : 'meses'})
                  </div>
                  <div className="text-lg font-semibold text-info">
                    {pred.data.metricas.venta_esperada != null ? fmt(pred.data.metricas.venta_esperada) : '—'}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-slate-500 mb-1">Mes Mayor Venta</div>
                  <div className="text-sm font-medium text-slate-200">{pred.data.metricas.mes_mayor_venta ?? '—'}</div>
                </div>
                <div>
                  <div className="text-xs text-slate-500 mb-1">Error MAE (ML)</div>
                  <div className="text-sm font-medium text-slate-200">
                    {pred.data.metricas.mae_modelo != null ? `± ${fmt(pred.data.metricas.mae_modelo)}` : '—'}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {pred.loading && (
        <div className="card p-12 text-center text-slate-400 border border-slate-700/50">
           Generando inferencias y conectando al Data Warehouse...
        </div>
      )}
      {pred.error && (
        <ErrorState message={pred.error} onRetry={pred.refetch} />
      )}

      {/* Secondary Charts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Ingresos por Categoría */}
        <ChartCard
          title="Ingresos por Categoría"
          badge={{ label: 'DW PostgreSQL', variant: 'hist' }}
          loading={revCat.loading}
          error={revCat.error ?? undefined}
          onRetry={revCat.refetch}
          empty={!revCat.loading && !revCat.error && (revCat.data ?? []).length === 0}
        >
          <ResponsiveContainer width="100%" height={280}>
            <BarChart
              data={revCat.data || []}
              layout="vertical"
              margin={{ top: 4, right: 10, left: 10, bottom: 4 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} horizontal={false} />
              <XAxis type="number" hide />
              <YAxis
                type="category"
                dataKey="cat"
                tick={{ fill: chartTheme.axisLabel, fontSize: 11 }}
                width={100}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                cursor={{ fill: chartTheme.cursor }}
                content={({ active, payload, label }) => {
                  if (!active || !payload?.length) return null;
                  return (
                    <ChartTooltip
                      title={label}
                      rows={[{ label: 'Ingresos', value: `$${Number(payload[0].value).toLocaleString()}`, color: chartTheme.live }]}
                    />
                  );
                }}
              />
              <Bar dataKey="v" fill={chartTheme.live} radius={[0, 5, 5, 0]} barSize={18} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Distribución por Sucursal/Vendedor */}
        <ChartCard
          title={donutTitle}
          badge={{ label: 'DW PostgreSQL', variant: 'hist' }}
          loading={kpi.loading}
          error={kpi.error ?? undefined}
          onRetry={kpi.refetch}
          empty={!kpi.loading && !kpi.error && donutData.length === 0}
        >
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  return (
                    <ChartTooltip
                      title={payload[0].name}
                      rows={[{ label: 'Ingresos', value: `$${Number(payload[0].value).toLocaleString()}` }]}
                    />
                  );
                }}
              />
              <Legend verticalAlign="bottom" height={36} wrapperStyle={{ fontSize: '11px', color: chartTheme.axisLabel }} />
              <Pie
                data={donutData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                innerRadius={70}
                outerRadius={100}
                paddingAngle={4}
              >
                {donutData.map((_, index) => (
                  <Cell key={`cell-${index}`} fill={colorByIndex(index)} />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Impacto del módulo de Venta Cruzada (RN-CS2) -- reutiliza el mismo panel que Ventas,
          nunca montado antes en Gerencia pese a que el endpoint ya está abierto a este rol. */}
      <div className="card p-6">
        <CrossSellKpiPanel />
      </div>
    </div>
  );
};
