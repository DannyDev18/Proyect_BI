import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, Boxes, CalendarClock } from 'lucide-react';
import {
  Area, Brush, CartesianGrid, ComposedChart, Legend, Line,
  ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { KpiCard, KpiCardSkeleton } from '../components/ui/KpiCard';
import { ChartCard } from '../components/ui/ChartCard';
import { ChartTooltip } from '../components/ui/ChartTooltip';
import { Select } from '../components/ui/Select';
import { BodegaFilterBar } from '../components/bodega/BodegaFilterBar';
import { PrediccionComprasChart } from '../components/bodega/PrediccionComprasChart';
import { useKpisBodega, useSalidasForecast, useTopProductos } from '../hooks/bodega';
import { useBodegaFiltersStore, toQueryFilters } from '../store/bodegaFiltersStore';
import { pct } from '../utils/format';
import { chartTheme } from '../utils/chartTheme';

const tendencia = (v: number | null | undefined) =>
  v == null ? '—' : `${v > 0 ? '▲ +' : v < 0 ? '▼ ' : ''}${v.toFixed(1)}% vs mes anterior`;

export const DashboardBodega = () => {
  const store = useBodegaFiltersStore();
  const filters = useMemo(() => toQueryFilters(store), [store]);

  const kpis = useKpisBodega(filters);
  const [productoForecast, setProductoForecast] = useState<string | null>(null);
  const forecast = useSalidasForecast(filters, productoForecast);
  // Solo alimenta el selector de producto de G1 (abajo) -- el propio gráfico "Top 20
  // Productos con Mayor Salida" (G3) se retiró (docs/features/plan_reabastecimiento_
  // inteligente.md §7.2/F10): ordenaba por ventas, justo lo opuesto de lo que hace
  // falta para priorizar reposición; esa prioridad real vive ahora en
  // /bodega/reabastecimiento (Lista Inteligente, ordenada por riesgo de quiebre).
  const top = useTopProductos(filters, 20);

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
            <Tooltip content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null;
              const rows = payload
                .filter((p) => p.value != null && p.name !== 'banda')
                .map((p) => ({
                  label: p.name === 'real' ? 'Salidas reales' : p.name === 'pred' ? 'Predicción' : String(p.name),
                  value: `${Number(p.value).toLocaleString('es-EC')} uds`,
                  color: p.color,
                }));
              if (!rows.length) return null;
              return <ChartTooltip title={String(label)} rows={rows} />;
            }} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Area dataKey="banda" name="Banda de confianza" stroke="none" fill={chartTheme.ml} fillOpacity={0.15} connectNulls />
            <Line dataKey="real" name="Salidas reales" stroke={chartTheme.palette[0]} strokeWidth={2} dot={false} connectNulls={false}
              activeDot={{ r: 4, fill: chartTheme.palette[0], stroke: chartTheme.cardBg, strokeWidth: 2 }} />
            <Line dataKey="pred" name="Predicción" stroke={chartTheme.ml} strokeWidth={2} strokeDasharray="6 4" dot={false} connectNulls
              activeDot={{ r: 4, fill: chartTheme.ml, stroke: chartTheme.cardBg, strokeWidth: 2 }} />
            {forecast.data?.punto_reorden != null && (
              <ReferenceLine y={forecast.data.punto_reorden} stroke={chartTheme.danger} strokeDasharray="4 4"
                label={{ value: `Punto reorden (${forecast.data.punto_reorden})`, fill: chartTheme.danger, fontSize: 10, position: 'insideTopRight' }} />
            )}
            {forecast.data?.stock_actual != null && (
              <ReferenceLine y={forecast.data.stock_actual} stroke={chartTheme.success}
                label={{ value: `Stock actual (${forecast.data.stock_actual})`, fill: chartTheme.success, fontSize: 10, position: 'insideBottomRight' }} />
            )}
            {/* Zoom/selección de rango (F7.4) — serie temporal larga (histórico + predicción) */}
            <Brush dataKey="fecha" height={24} stroke="var(--color-primary)" fill="var(--color-bg-elevated)"
              tickFormatter={(f: string) => f.slice(5)} travellerWidth={8} />
          </ComposedChart>
        </ResponsiveContainer>
      </ChartCard>

      {/* F10 (docs/features/plan_reabastecimiento_inteligente.md §7.2/§8): G2 (Matriz
          Rotación×Margen) se retiró -- era análisis financiero puro, duplicaba el
          Dashboard Ejecutivo (H-10); su reemplazo real, la clasificación ABC/XYZ, ya
          vive en /bodega/reabastecimiento (Lista Inteligente), donde SÍ define una
          política de inventario accionable. G3 (Top 20 Productos con Mayor Salida) y
          G4 (Distribución de Salidas por Categoría) se retiraron -- G3 ordenaba por
          ventas (lo opuesto de priorizar por riesgo de quiebre) y G4 era descriptivo
          puro, sin ninguna acción derivada de él. */}
      <div className="card p-4 flex items-center justify-between gap-3 animate-fade-in-up">
        <p className="text-sm text-slate-400">
          La priorización de compra por riesgo real de quiebre (clasificación ABC/XYZ, stock de seguridad,
          punto de reorden) vive ahora en Reabastecimiento Inteligente.
        </p>
        <Link
          to="/bodega/reabastecimiento"
          className="px-3 py-1.5 text-xs font-semibold rounded-lg border border-primary/40 text-primary hover:bg-primary/10 transition-colors focus-ring whitespace-nowrap"
        >
          Ir a Reabastecimiento Inteligente →
        </Link>
      </div>

      {/* Predicción de compras del próximo mes (enlazada al filtro de categoría) */}
      <PrediccionComprasChart filters={filters} />
    </div>
  );
};
