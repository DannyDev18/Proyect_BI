import { useState } from 'react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar,
  PieChart, Pie, Cell, Legend
} from 'recharts';
import { DollarSign, TrendingUp, ShoppingBag, Target, Filter } from 'lucide-react';
import { useGerenciaKPIs, useSalesPrediction, useRevenueByCategory, useCategories, useVendedores } from '../hooks/gerencia';
import { KpiCard, KpiCardSkeleton } from '../components/ui/KpiCard';
import { ChartCard } from '../components/ui/ChartCard';
import { AlertBadge } from '../components/ui/AlertBadge';
import { fmt, fmtFull, fmtMoney, pct } from '../utils/format';
import { chartTooltipStyle, COLORS } from '../utils/chartTheme';

export const DashboardGerencia = () => {
  const [filters, setFilters] = useState({
    start_date: '',
    end_date: '',
    categoria: '',
    vendedor: '',
  });

  const kpi  = useGerenciaKPIs(filters);
  const pred = useSalesPrediction();
  const revCat = useRevenueByCategory(filters);
  const { data: categoriasLista } = useCategories();
  const { data: vendedoresLista } = useVendedores();

  // Calcular ingresos totales sumando todas las sucursales si existen
  const ingresosTotales = kpi.data?.ventas_por_sucursal 
    ? Object.values(kpi.data.ventas_por_sucursal).reduce((a, b) => a + b, 0)
    : 0;

  // Switch between Branch logic or Seller logic for the Donut Chart based on active branch filter
  // Updated: even when "Todas las Sucursales" is selected, show "Distribución por Vendedor" to align with goals and commissions
  const donutData = kpi.data?.ventas_por_vendedor
    ? Object.entries(kpi.data.ventas_por_vendedor).map(([name, value]) => ({ name, value }))
    : [];
      
  const donutTitle = "Distribución por Vendedor";

  const salud = kpi.data?.roi_estimado;
  const saludVariant = salud
    ? salud >= 20 ? 'success' : salud >= 10 ? 'warning' : 'critical'
    : 'neutral';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap justify-between items-center gap-3 animate-fade-in">
        <div>
          <h1 className="text-3xl font-display font-semibold text-slate-100">Visión Ejecutiva</h1>
          <p className="text-sm text-slate-500 mt-0.5">Datos consolidados del Data Warehouse · Modo tiempo real</p>
        </div>
        <AlertBadge variant="info" dot>Modelo Gradient Boosting activo</AlertBadge>
      </div>

      {/* Filter Bar */}
      <div className="p-4 bg-slate-800/50 rounded-lg border border-slate-700/50 flex flex-wrap gap-4 items-center">
        <div className="flex items-center gap-2 text-slate-400">
          <Filter className="w-4 h-4" />
          <span className="text-sm font-medium">Filtros:</span>
        </div>
        
        <input 
          type="date" 
          value={filters.start_date}
          onChange={(e) => setFilters(f => ({ ...f, start_date: e.target.value }))}
          className="bg-slate-900 border border-slate-700 text-sm text-slate-300 rounded p-1.5 focus:outline-none focus:border-teal-400"
          title="Fecha de Inicio"
        />
        <span className="text-slate-500">-</span>
        <input 
          type="date" 
          value={filters.end_date}
          onChange={(e) => setFilters(f => ({ ...f, end_date: e.target.value }))}
          className="bg-slate-900 border border-slate-700 text-sm text-slate-300 rounded p-1.5 focus:outline-none focus:border-teal-400"
          title="Fecha de Fin"
        />

        <select
          value={filters.vendedor}
          onChange={(e) => setFilters(f => ({ ...f, vendedor: e.target.value }))}
          className="bg-slate-900 border border-slate-700 text-sm text-slate-300 rounded p-1.5 focus:outline-none focus:border-teal-400 min-w-[150px]"
        >
          <option value="">Todos los Vendedores</option>
          {vendedoresLista?.map(vend => (
            <option key={vend} value={vend}>{vend}</option>
          ))}
        </select>

        <select
          value={filters.categoria}
          onChange={(e) => setFilters(f => ({ ...f, categoria: e.target.value }))}
          className="bg-slate-900 border border-slate-700 text-sm text-slate-300 rounded p-1.5 focus:outline-none focus:border-teal-400 min-w-[150px]"
        >
          <option value="">Todas las Categorías</option>
          {categoriasLista?.map(cat => (
            <option key={cat} value={cat}>{cat}</option>
          ))}
        </select>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        {kpi.loading ? (
          <>
            <KpiCardSkeleton />
            <KpiCardSkeleton />
            <KpiCardSkeleton />
            <KpiCardSkeleton />
          </>
        ) : kpi.error ? (
          <div className="col-span-4 card p-6 text-center text-red-400 text-sm">
            Error al cargar KPIs: {kpi.error}
          </div>
        ) : (
          <>
            <KpiCard
              title="Ingresos Totales (ventas-devoluciones)"
              value={kpi.data ? fmtMoney(ingresosTotales) : '—'}
              icon={DollarSign}
              trend="neutral"
              animDelay={0}
            />
            <KpiCard
              title="Margen de Utilidad"
              value={kpi.data ? pct(kpi.data.margen_utilidad_neta) : '—'}
              icon={TrendingUp}
              trend="up"
              animDelay={60}
            />
            <KpiCard
              title="Ticket Promedio"
              value={kpi.data ? fmt(kpi.data.ticket_promedio) : '—'}
              icon={ShoppingBag}
              trend="neutral"
              animDelay={120}
            />
            <KpiCard
              title="Proyección ROI"
              value={kpi.data ? pct(kpi.data.roi_estimado) : '—'}
              icon={Target}
              trend={saludVariant === 'success' ? 'up' : saludVariant === 'critical' ? 'down' : 'neutral'}
              animDelay={180}
            />
          </>
        )}
      </div>

      {/* Panel Ejecutivo de Predicción */}
      {pred.data && !pred.loading && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 animate-fade-in">
          <div className="col-span-1 md:col-span-2">
            <ChartCard
              title="Histórico y Predicción de Ventas (ML)"
              badge={{ label: 'Gradient Boosting', variant: 'ml' }}
            >
              <ResponsiveContainer width="100%" height={380}>
                <AreaChart
                  data={pred.data.historial_y_prediccion}
                  margin={{ top: 20, right: 30, left: 0, bottom: 0 }}
                >
                  <defs>
                    <linearGradient id="gradHist" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="gradPred" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.4} />
                      <stop offset="95%" stopColor="#06b6d4" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                  <XAxis
                    dataKey="fecha"
                    stroke="#334155"
                    tick={{ fill: '#64748b', fontSize: 11 }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(v) => v?.slice(5) ?? v}
                    minTickGap={30}
                  />
                  <YAxis
                    stroke="#334155"
                    tick={{ fill: '#64748b', fontSize: 11 }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(v) => `$${v / 1000}k`}
                    width={55}
                  />
                  <Tooltip {...chartTooltipStyle} formatter={(value, name) => [`$${Number(value).toLocaleString(undefined, {minimumFractionDigits: 2})}`, name === 'monto_real' ? 'Real' : name === 'monto_predicho' ? 'Predicho' : name]} />
                  <Legend verticalAlign="top" height={36} wrapperStyle={{ fontSize: '12px', color: '#94a3b8' }} />
                  
                  {/* Historic Area */}
                  <Area
                    connectNulls={true}
                    type="monotone"
                    dataKey="monto_real"
                    stroke="#3b82f6"
                    strokeWidth={2.5}
                    fill="url(#gradHist)"
                    name="Histórico Real"
                    dot={false}
                    activeDot={{ r: 4, fill: '#3b82f6', stroke: '#0f172a', strokeWidth: 2 }}
                  />
                  
                  {/* Prediction Area */}
                  <Area
                  connectNulls={true}
                    type="monotone"
                    dataKey="monto_predicho"
                    stroke="#06b6d4"
                    strokeWidth={2.5}
                    strokeDasharray="5 5"
                    fill="url(#gradPred)"
                    name="Predicción Futura"
                    dot={false}
                    activeDot={{ r: 6, fill: '#06b6d4', stroke: '#0f172a', strokeWidth: 2 }}
                  />
                  
                  {/* Confidence Interval Lines */}
                  {pred.data.historial_y_prediccion.some(d => d.intervalo_superior) && (
                    <>
                      <Area type="monotone" dataKey="intervalo_superior" stroke="#06b6d4" strokeWidth={1} strokeDasharray="3 3" fill="none" name="Límite Superior (95%)" dot={false} />
                      <Area type="monotone" dataKey="intervalo_inferior" stroke="#06b6d4" strokeWidth={1} strokeDasharray="3 3" fill="none" name="Límite Inferior (95%)" dot={false} />
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
                <Target className="w-5 h-5 text-teal-400" /> Inteligencia Comercial
              </h3>
              <ul className="space-y-4 text-sm text-slate-300">
                {pred.data.insights.map((insight, idx) => (
                  <li key={idx} className="flex gap-3">
                    <span className="flex-shrink-0 w-1.5 h-1.5 mt-2 rounded-full bg-teal-400"></span>
                    <span className="leading-snug">{insight}</span>
                  </li>
                ))}
              </ul>
              
              <div className="mt-6 pt-6 border-t border-slate-700/50 grid grid-cols-2 gap-4">
                <div>
                  <div className="text-xs text-slate-500 mb-1">Crecimiento Est.</div>
                  <div className={`text-lg font-semibold ${pred.data.metricas.crecimiento_esperado > 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {pred.data.metricas.crecimiento_esperado > 0 ? '+' : ''}{pred.data.metricas.crecimiento_esperado.toFixed(1)}%
                  </div>
                </div>
                <div>
                  <div className="text-xs text-slate-500 mb-1">Proyección ({pred.data.dias_proyectados}d)</div>
                  <div className="text-lg font-semibold text-sky-400">{fmt(pred.data.metricas.venta_esperada)}</div>
                </div>
                <div>
                  <div className="text-xs text-slate-500 mb-1">Mes Mayor Venta</div>
                  <div className="text-sm font-medium text-slate-200">{pred.data.metricas.mes_mayor_venta}</div>
                </div>
                <div>
                  <div className="text-xs text-slate-500 mb-1">Error MAE (ML)</div>
                  <div className="text-sm font-medium text-slate-200">± {fmt(pred.data.metricas.mae_modelo)}</div>
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
        <div className="card p-6 border border-rose-500/20 bg-rose-500/5 flex flex-col items-center">
           <p className="text-rose-400 font-medium">Error de conexión al modelo</p>
           <p className="text-sm text-rose-400/80">{pred.error}</p>
        </div>
      )}

      {/* Secondary Charts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Ingresos por Categoría */}
        <ChartCard title="Ingresos por Categoría" badge={{ label: 'DW PostgreSQL', variant: 'hist' }} loading={revCat.loading}>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart
              data={revCat.data || []}
              layout="vertical"
              margin={{ top: 4, right: 10, left: 10, bottom: 4 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
              <XAxis type="number" hide />
              <YAxis
                type="category"
                dataKey="cat"
                tick={{ fill: '#94a3b8', fontSize: 11 }}
                width={100}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                {...chartTooltipStyle}
                cursor={{ fill: '#1e293b' }}
                formatter={(v: any) => [`$${Number(v).toLocaleString()}`, 'Ingresos']}
              />
              <Bar dataKey="v" fill="#06b6d4" radius={[0, 5, 5, 0]} barSize={18} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Distribución por Sucursal/Vendedor */}
        <ChartCard title={donutTitle} badge={{ label: 'DW PostgreSQL', variant: 'hist' }} loading={kpi.loading}>
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Tooltip {...chartTooltipStyle} formatter={(v: any) => [`$${Number(v).toLocaleString()}`, 'Ingresos']} />
              <Legend verticalAlign="bottom" height={36} wrapperStyle={{ fontSize: '11px', color: '#94a3b8' }} />
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
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
    </div>
  );
};
