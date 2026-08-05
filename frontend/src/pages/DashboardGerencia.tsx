import { useMemo, useState } from 'react';
import {
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, Line, ComposedChart,
  PieChart, Pie, Cell, Legend, Brush
} from 'recharts';
import { DollarSign, TrendingUp, ShoppingBag, Target, FileSpreadsheet } from 'lucide-react';
import {
  useGerenciaKPIs, useEvolucionMensualVentas, useRevenueByCategory, useCategories, useVendedores, useAlmacenes,
} from '../hooks/gerencia';
import { descargarReporteDashboardExcel } from '../services/gerencia';
import { MODO_COMPARACION_LABEL, type ModoComparacion } from '../types/gerencia';
import { KpiCard, KpiCardSkeleton } from '../components/ui/KpiCard';
import { ChartCard } from '../components/ui/ChartCard';
import { Badge } from '../components/ui/Badge';
import { Select } from '../components/ui/Select';
import { DateField } from '../components/ui/DateField';
import { FilterBar, FilterField } from '../components/ui/FilterBar';
import { Button } from '../components/ui/Button';
import { ChartTooltip } from '../components/ui/ChartTooltip';
import { ErrorState } from '../components/ui/ErrorState';
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
    // G-04: período de referencia de las tendencias. Solo aplica con fechas explícitas.
    modo_comparacion: 'periodo_anterior' as ModoComparacion,
  });
  const [ventanaMeses, setVentanaMeses] = useState<12 | 24>(24);
  const [descargando, setDescargando] = useState(false);
  const toast = useToast();

  const kpi  = useGerenciaKPIs(filters);
  // Auditoría 49 (decomisión de `sales_rf`): reemplaza al panel de predicción ML por
  // histórico real mes a mes -- sin ningún modelo.
  const evolucion = useEvolucionMensualVentas({ vendedor: filters.vendedor, almacen: filters.almacen, meses: ventanaMeses });
  const revCat = useRevenueByCategory(filters);
  const { data: categoriasLista } = useCategories();
  const { data: vendedoresLista } = useVendedores();
  const { data: almacenesLista } = useAlmacenes();

  // Promedio móvil de 3 meses -- aritmética simple sobre la serie real (no un modelo),
  // es la "línea" del gráfico de barras+líneas que pidió el usuario.
  const evolucionConPromedio = useMemo(() => {
    const serie = evolucion.data ?? [];
    return serie.map((punto, idx) => {
      const ventana = serie.slice(Math.max(0, idx - 2), idx + 1);
      const promedio = ventana.reduce((acc, p) => acc + p.venta_neta, 0) / ventana.length;
      return {
        fecha: `${punto.anio}-${String(punto.mes).padStart(2, '0')}-01`,
        venta_neta: punto.venta_neta,
        promedio_movil_3m: promedio,
      };
    });
  }, [evolucion.data]);

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
  // dashboard a Excel real (backend, reutiliza warehouse_export.py).
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

  // docs/auditoria/39_madurez_bi_toma_decisiones.md, H-02: `roi_real` (RN-BI2) reemplaza al
  // antiguo `roi_estimado`. Es nullable a propósito: `null` = no hay costo de mercadería
  // con el que comparar, y se comunica explícitamente en vez de pintar un 0% falso.
  const salud = kpi.data?.roi_real ?? null;
  const saludVariant = salud !== null
    ? salud >= 20 ? 'success' : salud >= 10 ? 'warning' : 'danger'
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
          <Badge variant="info" dot>
            Datos reales del Data Warehouse
          </Badge>
          <Button
            variant="success" size="sm" onClick={exportarExcel} disabled={kpi.loading}
            loading={descargando} icon={!descargando ? <FileSpreadsheet size={14} aria-hidden="true" /> : undefined}
            aria-label="Exportar reporte del dashboard a Excel"
          >
            {descargando ? 'Generando…' : 'Excel'}
          </Button>
        </div>
      </div>

      {/* Filter Bar */}
      <FilterBar className="print:hidden">
    

        <FilterField label="Desde" htmlFor="gerencia-fecha-desde">
          <DateField
            id="gerencia-fecha-desde"
            value={filters.start_date}
            onChange={(e) => setFilters(f => ({ ...f, start_date: e.target.value }))}
          />
        </FilterField>
        <FilterField label="Hasta" htmlFor="gerencia-fecha-hasta">
          <DateField
            id="gerencia-fecha-hasta"
            value={filters.end_date}
            onChange={(e) => setFilters(f => ({ ...f, end_date: e.target.value }))}
          />
        </FilterField>

        <FilterField label="Vendedor">
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
        </FilterField>

        <FilterField label="Categoría">
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
        </FilterField>

        <FilterField label="Almacén">
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
        </FilterField>
       
      </FilterBar>

      {/* G-04: decir explícitamente contra qué se compara. Sin esto, una variación de "+14%"
          no significa nada -- ¿contra el mes pasado o contra el año pasado? */}
      {kpi.data?.comparacion && (
        <p className="text-xs text-slate-500">
          Las variaciones comparan contra{' '}
          <span className="text-slate-400 font-medium">
            {MODO_COMPARACION_LABEL[kpi.data.comparacion.modo].toLowerCase()}
          </span>{' '}
          ({kpi.data.comparacion.desde_referencia} a {kpi.data.comparacion.hasta_referencia}
          {kpi.data.comparacion.periodos_promediados > 1
            ? `, ${kpi.data.comparacion.periodos_promediados} períodos promediados`
            : ''}).
          {kpi.data.comparacion.sin_base && (
            <span className="text-warning"> Algunos indicadores no tienen base comparable.</span>
          )}
        </p>
      )}
      {!filters.start_date || !filters.end_date ? (
        <p className="text-xs text-slate-600">
          Fija un rango de fechas para ver la variación de cada indicador contra un período de referencia.
        </p>
      ) : null}

      {/* KPI Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 stagger-children">
        {kpi.loading ? (
          <>
            <KpiCardSkeleton />
            <KpiCardSkeleton />
            <KpiCardSkeleton />
            <KpiCardSkeleton />
          </>
        ) : kpi.error ? (
          <div className="col-span-4">
            <ErrorState message={`Error al cargar KPIs: ${kpi.error}`} onRetry={kpi.refetch} />
          </div>
        ) : (
          <>
            <KpiCard
              title="Ingresos Totales (ventas-devoluciones)"
              value={kpi.data ? fmtMoney(kpi.data.ingresos_totales) : '—'}
              icon={DollarSign}
              tooltip="Últimos meses de venta neta real, misma serie del gráfico de evolución mensual"
              sparkline={evolucion.data?.map((d) => d.venta_neta).slice(-12)}
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
              title="ROI sobre costo de mercadería"
              value={kpi.data ? (salud !== null ? pct(salud) : 'Sin base') : '—'}
              icon={Target}
              state={kpi.data ? saludVariant === 'neutral' ? undefined : saludVariant : undefined}
              trend={
                kpi.data?.roi_real_tendencia_pct != null
                  ? tendencia(kpi.data.roi_real_tendencia_pct).trend
                  : saludVariant === 'success' ? 'up' : saludVariant === 'danger' ? 'down' : 'neutral'
              }
              subValue={
                kpi.data && salud === null
                  ? 'Sin costo de mercadería en el período'
                  : tendencia(kpi.data?.roi_real_tendencia_pct).subValue
              }
            />
          </>
        )}
      </div>

      {/* Evolución mensual de ventas -- reemplaza al panel de predicción ML retirado
          (auditoría 49, decomisión de `sales_rf`): 100% histórico real (Venta Neta),
          sin ningún modelo. Barras = venta neta del mes; línea = promedio móvil de 3
          meses (aritmética simple sobre la misma serie, calculada en el frontend). */}
      <ChartCard
        title="Evolución mensual de ventas"
        badge={{ label: 'DW PostgreSQL', variant: 'hist' }}
        loading={evolucion.loading}
        error={evolucion.error ?? undefined}
        onRetry={evolucion.refetch}
        empty={!evolucion.loading && !evolucion.error && evolucionConPromedio.length === 0}
        actions={
          <div className="flex items-center gap-1 bg-slate-800/70 border border-slate-700/50 rounded-full p-0.5">
            {([12, 24] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setVentanaMeses(m)}
                className={`px-3 py-1 text-xs font-medium rounded-full transition-colors focus-ring ${
                  ventanaMeses === m ? 'bg-primary/20 text-primary' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {m} meses
              </button>
            ))}
          </div>
        }
      >
        <p className="text-xs text-slate-500 mb-3 -mt-2">
          Venta Neta real (ventas - devoluciones) por mes; respeta los filtros de{' '}
          <span className="text-slate-400 font-medium">vendedor</span> y{' '}
          <span className="text-slate-400 font-medium">almacén</span> de arriba.
        </p>
        <ResponsiveContainer width="100%" height={380}>
          <ComposedChart data={evolucionConPromedio} margin={{ top: 20, right: 30, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} vertical={false} />
            <XAxis
              dataKey="fecha"
              stroke={chartTheme.grid}
              tick={axisTick}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => formatEjeFecha(v, 'mes')}
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
                    label: p.dataKey === 'venta_neta' ? 'Venta Neta' : 'Promedio móvil (3m)',
                    value: `$${Number(p.value).toLocaleString(undefined, { minimumFractionDigits: 2 })}`,
                    color: p.color,
                  }));
                return <ChartTooltip title={formatEjeFecha(String(label), 'mes')} rows={rows} />;
              }}
            />
            <Legend verticalAlign="top" height={36} wrapperStyle={{ fontSize: '12px', color: chartTheme.axisLabel }} />
            <Bar dataKey="venta_neta" name="Venta Neta" fill={chartTheme.palette[0]} radius={[4, 4, 0, 0]} />
            <Line
              type="monotone"
              dataKey="promedio_movil_3m"
              name="Promedio móvil (3m)"
              stroke={chartTheme.live}
              strokeWidth={2.5}
              dot={false}
              activeDot={{ r: 5, fill: chartTheme.live, stroke: chartTheme.cardBg, strokeWidth: 2 }}
            />
            <Brush
              dataKey="fecha"
              height={24}
              stroke="var(--color-primary)"
              fill="var(--color-bg-elevated)"
              tickFormatter={(v) => formatEjeFecha(String(v), 'mes')}
              travellerWidth={8}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </ChartCard>

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
    </div>
  );
};
