import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, Boxes, CalendarClock } from 'lucide-react';
import {
  Area, Bar, BarChart, CartesianGrid, Cell, ComposedChart, Legend, Line, Pie, PieChart,
  ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from 'recharts';
import { KpiCard, KpiCardSkeleton } from '../components/ui/KpiCard';
import { ChartCard } from '../components/ui/ChartCard';
import { Select } from '../components/ui/Select';
import { BodegaFilterBar } from '../components/bodega/BodegaFilterBar';
import { PrediccionComprasChart } from '../components/bodega/PrediccionComprasChart';
import {
  useKpisBodega, useRotacionMatriz, useSalidasCategoria, useSalidasForecast, useTopProductos,
} from '../hooks/bodega';
import { useBodegaFiltersStore, toQueryFilters } from '../store/bodegaFiltersStore';
import { fmt, pct } from '../utils/format';
import { chartTheme, colorByCategory } from '../utils/chartTheme';

const tooltipStyle = {
  backgroundColor: chartTheme.cardBg, borderColor: chartTheme.grid, borderRadius: '8px', fontSize: '12px',
} as const;

const tendencia = (v: number | null | undefined) =>
  v == null ? '—' : `${v > 0 ? '▲ +' : v < 0 ? '▼ ' : ''}${v.toFixed(1)}% vs mes anterior`;

export const DashboardBodega = () => {
  const store = useBodegaFiltersStore();
  const filters = useMemo(() => toQueryFilters(store), [store]);

  const kpis = useKpisBodega(filters);
  const [productoForecast, setProductoForecast] = useState<string | null>(null);
  const forecast = useSalidasForecast(filters, productoForecast);
  const rotacion = useRotacionMatriz(filters);
  const top = useTopProductos(filters, 20);
  const categorias = useSalidasCategoria(filters);

  // G1: fusiona histórico + predicción en una sola serie para el ComposedChart.
  const serieForecast = useMemo(() => {
    if (!forecast.data) return [];
    const hist = forecast.data.historial.map((h) => ({
      fecha: h.fecha, real: h.unidades, pred: null as number | null, banda: null as [number, number] | null,
    }));
    const preds = forecast.data.prediccion.map((p) => ({
      fecha: p.fecha, real: null, pred: p.unidades, banda: [p.banda_inferior, p.banda_superior] as [number, number],
    }));
    // Pivote sin gap visual entre real y predicción.
    if (hist.length && preds.length) hist[hist.length - 1].pred = hist[hist.length - 1].real;
    return [...hist, ...preds];
  }, [forecast.data]);

  const nombresCategorias = useMemo(
    () => (categorias.data ?? []).map((c) => c.categoria),
    [categorias.data],
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap justify-between items-center gap-3 animate-fade-in">
        <div>
          <h1 className="text-3xl font-display font-semibold text-slate-100">Gestión de Inventario y Abastecimiento</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Decisiones de compra y transferencia basadas en histórico del EDW + predicción ML
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link to="/bodega/almacenes" className="px-3 py-1.5 text-xs font-semibold rounded-lg border border-slate-700 text-slate-300 hover:border-primary hover:text-primary transition-colors focus-ring">
            Status por Almacén
          </Link>
          <Link to="/bodega/reportes" className="px-3 py-1.5 text-xs font-semibold rounded-lg border border-slate-700 text-slate-300 hover:border-primary hover:text-primary transition-colors focus-ring">
            Reportes Gerencia
          </Link>
        </div>
      </div>

      {/* §1.1 Filtros globales */}
      <BodegaFilterBar />

      {/* §1.2 KPIs — cobertura operativa (3): qué tengo, qué falta reponer, cuánto dura */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 stagger-children">
        {kpis.loading ? (
          <><KpiCardSkeleton /><KpiCardSkeleton /><KpiCardSkeleton /></>
        ) : kpis.error ? (
          <div className="col-span-full card p-4 text-danger text-sm">{kpis.error}</div>
        ) : kpis.data && (
          <>
            <KpiCard title="Artículos en Inventario" icon={Boxes}
              value={kpis.data.total_articulos.skus_activos.toLocaleString('es-EC')}
              subValue={`${kpis.data.total_articulos.cantidad_total.toLocaleString('es-EC', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} unidades · de ${kpis.data.total_articulos.total_skus.toLocaleString('es-EC')} en catálogo · ${kpis.data.total_articulos.skus_stock_cero} en cero · ${tendencia(kpis.data.total_articulos.tendencia_pct)}`}
              trend={(kpis.data.total_articulos.tendencia_pct ?? 0) >= 0 ? 'up' : 'down'} />
            <KpiCard title="Productos con Stock Bajo" icon={AlertTriangle}
              value={kpis.data.stock_bajo.productos_bajo_reorden}
              subValue={`${pct(kpis.data.stock_bajo.pct_del_total)} del catálogo bajo punto de reorden`}
              trend={kpis.data.stock_bajo.color === 'verde' ? 'up' : kpis.data.stock_bajo.color === 'amarillo' ? 'neutral' : 'down'} />
            <KpiCard title="Días de Inventario" icon={CalendarClock}
              value={kpis.data.dias_inventario.dias != null ? `${kpis.data.dias_inventario.dias} días` : '—'}
              subValue={kpis.data.dias_inventario.alerta_desabastecimiento ? '⚠ Riesgo de desabastecimiento (<15 días)' : 'Cobertura saludable'}
              trend={kpis.data.dias_inventario.alerta_desabastecimiento ? 'down' : 'up'} />
          </>
        )}
      </div>

      {/* G1: Histórico + predicción de salidas */}
      <ChartCard
        title="Histórico y Predicción de Salidas"
        badge={{ label: forecast.data?.metodo === 'ml_demand_rf' ? 'ML demand_rf' : 'Proyección estadística', variant: 'ml' }}
        height="h-[360px]"
        loading={forecast.loading}
        error={forecast.error ?? undefined}
        onRetry={forecast.refetch}
        empty={!forecast.loading && !forecast.error && serieForecast.length === 0}
        emptyDescription="No hay histórico de salidas para el producto o filtros seleccionados."
        actions={
          <Select
            size="sm"
            aria-label="Producto para el forecast"
            value={productoForecast ?? 'TOP'}
            onChange={(e) => setProductoForecast(e.target.value === 'TOP' ? null : e.target.value)}
          >
            <option value="TOP">Top 10 productos (agregado)</option>
            {(top.data ?? []).map((p) => (
              <option key={p.codart} value={p.codart}>{p.codart} — {p.nombre.slice(0, 40)}</option>
            ))}
          </Select>
        }
      >
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={serieForecast} margin={{ top: 4, right: 16, left: -10, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} vertical={false} />
            <XAxis dataKey="fecha" tick={{ fill: chartTheme.axis, fontSize: 10 }} tickFormatter={(f: string) => f.slice(5)} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: chartTheme.axis, fontSize: 11 }} axisLine={false} tickLine={false} />
            <Tooltip contentStyle={tooltipStyle} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Area dataKey="banda" name="Banda de confianza" stroke="none" fill={chartTheme.ml} fillOpacity={0.15} connectNulls />
            <Line dataKey="real" name="Salidas reales" stroke={chartTheme.palette[0]} strokeWidth={2} dot={false} connectNulls={false} />
            <Line dataKey="pred" name="Predicción" stroke={chartTheme.ml} strokeWidth={2} strokeDasharray="6 4" dot={false} connectNulls />
            {forecast.data?.punto_reorden != null && (
              <ReferenceLine y={forecast.data.punto_reorden} stroke={chartTheme.danger} strokeDasharray="4 4"
                label={{ value: `Punto reorden (${forecast.data.punto_reorden})`, fill: chartTheme.danger, fontSize: 10, position: 'insideTopRight' }} />
            )}
            {forecast.data?.stock_actual != null && (
              <ReferenceLine y={forecast.data.stock_actual} stroke={chartTheme.success}
                label={{ value: `Stock actual (${forecast.data.stock_actual})`, fill: chartTheme.success, fontSize: 10, position: 'insideBottomRight' }} />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </ChartCard>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {/* G2: Matriz rotación × margen */}
        <ChartCard title="Matriz de Rotación y Rentabilidad" badge={{ label: 'Cuadrantes de prioridad', variant: 'hist' }} height="h-[340px]"
          loading={rotacion.loading} error={rotacion.error ?? undefined} onRetry={rotacion.refetch}
          empty={!rotacion.loading && !rotacion.error && (rotacion.data?.productos ?? []).length === 0}>
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 10, right: 16, left: -10, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} />
              <XAxis type="number" dataKey="rotacion_mensual" name="Rotación mensual" tick={{ fill: chartTheme.axis, fontSize: 11 }}
                label={{ value: 'Rotación (veces/mes)', fill: chartTheme.axis, fontSize: 11, position: 'insideBottom', offset: -2 }} />
              <YAxis type="number" dataKey="margen_unitario" name="Margen/unidad" tick={{ fill: chartTheme.axis, fontSize: 11 }}
                label={{ value: 'Margen $/ud', fill: chartTheme.axis, fontSize: 11, angle: -90, position: 'insideLeft' }} />
              <ZAxis type="number" dataKey="valor_inventario" range={[40, 400]} name="Valor inventario" />
              <Tooltip
                contentStyle={tooltipStyle}
                content={({ payload }) => {
                  const p = payload?.[0]?.payload;
                  if (!p) return null;
                  return (
                    <div style={tooltipStyle} className="p-3 border">
                      <p className="font-semibold text-slate-200">{p.nombre}</p>
                      <p className="text-slate-400">Rotación: {p.rotacion_mensual ?? '—'} veces/mes</p>
                      <p className="text-slate-400">Margen: ${p.margen_unitario}/ud</p>
                      <p className="text-slate-400">Stock: {p.stock_actual} · Días inv: {p.dias_inventario ?? '∞'}</p>
                      <p className="text-slate-400">Valor: {fmt(p.valor_inventario)}</p>
                    </div>
                  );
                }}
              />
              {rotacion.data && (
                <>
                  <ReferenceLine x={rotacion.data.mediana_rotacion} stroke={chartTheme.median} strokeDasharray="4 4" />
                  <ReferenceLine y={rotacion.data.mediana_margen} stroke={chartTheme.median} strokeDasharray="4 4" />
                </>
              )}
              <Scatter data={(rotacion.data?.productos ?? []).filter((p) => p.rotacion_mensual != null)} fill={chartTheme.live} fillOpacity={0.6} />
            </ScatterChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* G4: Distribución por categoría */}
        <ChartCard title="Distribución de Salidas por Categoría" badge={{ label: 'vs período anterior', variant: 'hist' }} height="h-[340px]"
          loading={categorias.loading} error={categorias.error ?? undefined} onRetry={categorias.refetch}
          empty={!categorias.loading && !categorias.error && (categorias.data ?? []).length === 0}>
          <div className="flex h-full gap-4">
            <ResponsiveContainer width="55%" height="100%">
              <PieChart>
                <Pie data={categorias.data ?? []} dataKey="unidades" nameKey="categoria" innerRadius="45%" outerRadius="80%" paddingAngle={2}>
                  {(categorias.data ?? []).map((c) => (
                    <Cell key={c.categoria} fill={colorByCategory(c.categoria, nombresCategorias)} stroke="none" />
                  ))}
                </Pie>
                <Tooltip contentStyle={tooltipStyle}
                  content={({ payload }) => {
                    const p = payload?.[0]?.payload as { categoria?: string; unidades?: number; pct_participacion?: number; monto_ventas?: number | null } | undefined;
                    if (!p) return null;
                    return (
                      <div style={tooltipStyle} className="p-3 border">
                        <p className="font-semibold text-slate-200">{p.categoria}</p>
                        <p className="text-slate-400">{(p.unidades ?? 0).toLocaleString('es-EC')} uds ({p.pct_participacion ?? 0}%)</p>
                        {p.monto_ventas != null && <p className="text-success">Monto: {fmt(p.monto_ventas)}</p>}
                      </div>
                    );
                  }} />
              </PieChart>
            </ResponsiveContainer>
            <div className="flex-1 overflow-y-auto text-xs space-y-2 pr-1">
              {(categorias.data ?? []).map((c) => (
                <div key={c.categoria} className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-1.5 text-slate-300">
                    <span className="w-2.5 h-2.5 rounded-sm" style={{ background: colorByCategory(c.categoria, nombresCategorias) }} />
                    {c.categoria}
                  </span>
                  <span className="text-slate-500 font-mono">
                    {c.pct_participacion}% · {c.tendencia_pct != null ? `${c.tendencia_pct > 0 ? '+' : ''}${c.tendencia_pct}%` : '—'} · stock {c.stock_disponible.toLocaleString('es-EC')}
                    {c.monto_ventas != null ? ` · ${fmt(c.monto_ventas)}` : ''}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </ChartCard>
      </div>

      {/* G3: Top 20 productos */}
      <ChartCard title="Top 20 Productos con Mayor Salida" badge={{ label: 'Prioridad de abastecimiento', variant: 'hist' }}
        height="h-[560px]" loading={top.loading} error={top.error ?? undefined} onRetry={top.refetch}
        empty={!top.loading && !top.error && (top.data ?? []).length === 0}
        actions={<Link to="/bodega/almacenes" className="text-xs text-primary hover:underline focus-ring rounded">Ver todos los productos →</Link>}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={top.data ?? []} layout="vertical" margin={{ top: 4, right: 90, left: 40, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} horizontal={false} />
            <XAxis type="number" tick={{ fill: chartTheme.axis, fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis type="category" dataKey="nombre" width={180} tick={{ fill: chartTheme.axisLabel, fontSize: 10 }}
              tickFormatter={(n: string) => n.length > 26 ? `${n.slice(0, 26)}…` : n} axisLine={false} tickLine={false} />
            <Tooltip contentStyle={tooltipStyle} cursor={{ fill: chartTheme.grid }}
              content={({ payload }) => {
                const p = payload?.[0]?.payload;
                if (!p) return null;
                return (
                  <div style={tooltipStyle} className="p-3 border">
                    <p className="font-semibold text-slate-200">{p.nombre} <span className="text-slate-500">({p.codart})</span></p>
                    <p className="text-slate-400">Salidas: {p.unidades.toLocaleString('es-EC')} uds {p.tendencia_pct != null && (p.tendencia_pct >= 0 ? `↑ +${p.tendencia_pct}%` : `↓ ${p.tendencia_pct}%`)}</p>
                    {p.monto_ventas != null && <p className="text-success">Monto: {fmt(p.monto_ventas)}</p>}
                    <p className="text-slate-400">Stock: {p.stock_actual} uds · {p.dias_inventario != null ? `${p.dias_inventario} días` : 'sin consumo'}</p>
                  </div>
                );
              }} />
            <Bar dataKey="unidades" radius={[0, 4, 4, 0]} barSize={16}>
              {(top.data ?? []).map((p) => (
                <Cell key={p.codart} fill={colorByCategory(p.categoria, nombresCategorias)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>

      {/* Predicción de compras del próximo mes (enlazada al filtro de categoría) */}
      <PrediccionComprasChart filters={filters} />
    </div>
  );
};
