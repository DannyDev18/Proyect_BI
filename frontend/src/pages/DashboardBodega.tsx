import { useState } from 'react';
import { AlertTriangle, Package, TrendingUp, ShieldAlert } from 'lucide-react';
import { useBodegaKPIs, useDemandForecast } from '../hooks/bodega';
import { KpiCard, KpiCardSkeleton } from '../components/ui/KpiCard';
import { ChartCard } from '../components/ui/ChartCard';
import { AlertBadge } from '../components/ui/AlertBadge';
import { SearchInput } from '../components/ui/SearchInput';
import { GlobalBranchSelector } from '../components/ui/GlobalBranchSelector';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts';
import { useAuthStore } from '../store/authStore';
import { MOCK_ALERTS } from '../services/mocks/bodega.mock';
import { fmt } from '../utils/format';

export const DashboardBodega = () => {
  const { user } = useAuthStore();
  const kpi     = useBodegaKPIs();
  const demand  = useDemandForecast();
  const [skuBuscado, setSkuBuscado] = useState('');
  const [sucursal, setSucursal] = useState<string | null>(null);
  
  // isAdmin checks if the user is strict admin to enable destructive actions.
  const isAdmin = user?.role === 'administrador';

  const handleSkuSearch = (sku: string) => {
    setSkuBuscado(sku);
    demand.execute(sku);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap justify-between items-center gap-3 animate-fade-in">
        <div>
          <h1 className="text-3xl font-display font-semibold text-slate-100">Control de Inventario</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Sucursal: <span className="text-slate-300">{user?.role === 'gerencia' || user?.role === 'administrador' ? (sucursal || 'Consolidado Global') : (user?.sucursalId ?? 'Central')}</span> · Predicción de demanda por SKU activa
          </p>
        </div>
        <div className="flex items-center gap-4">
          <GlobalBranchSelector onSelectSucursal={setSucursal} />
          {(kpi.data?.alertas_criticas ?? 0) > 0 && (
            <AlertBadge variant="critical" dot>
              {kpi.data?.alertas_criticas} alertas críticas
            </AlertBadge>
          )}
        </div>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        {kpi.loading ? (
          <><KpiCardSkeleton /><KpiCardSkeleton /><KpiCardSkeleton /><KpiCardSkeleton /></>
        ) : kpi.error ? (
          <div className="col-span-4 card p-4 text-red-400 text-sm">{kpi.error}</div>
        ) : (
          <>
            <KpiCard
              title="Ítems en Riesgo"
              value={kpi.data?.items_riesgo_desabastecimiento ?? '—'}
              icon={AlertTriangle}
              trend={(kpi.data?.items_riesgo_desabastecimiento ?? 0) > 10 ? 'down' : 'neutral'}
              animDelay={0}
            />
            <KpiCard
              title="Sobrestock"
              value={kpi.data?.items_sobrestock ?? '—'}
              icon={Package}
              trend={(kpi.data?.items_sobrestock ?? 0) > 20 ? 'down' : 'neutral'}
              animDelay={60}
            />
            <KpiCard
              title="Valorización"
              value={kpi.data ? fmt(kpi.data.valorizacion_inventario) : '—'}
              icon={ShieldAlert}
              trend="neutral"
              animDelay={120}
            />
            <KpiCard
              title="Rotación Mensual"
              value={kpi.data ? `${kpi.data.rotacion_mensual.toFixed(1)}x` : '—'}
              icon={TrendingUp}
              trend={kpi.data && kpi.data.rotacion_mensual >= 4 ? 'up' : 'down'}
              animDelay={180}
            />
          </>
        )}
      </div>

      {/* SKU Demand Forecasting */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card p-6 animate-fade-in-up stagger-1">
          <h3 className="font-sans font-semibold text-slate-200 mb-4">Predicción de Demanda por SKU</h3>
          <SearchInput
            placeholder="Ej: TEC-0012"
            onSearch={handleSkuSearch}
            loading={demand.loading}
            label="Código de producto (SKU)"
          />
          {skuBuscado && (
            <div className="mt-5">
              {demand.loading && <p className="text-cyan-400 text-sm animate-pulse-slow">Consultando modelo…</p>}
              {demand.error && <p className="text-red-400 text-sm">{demand.error}</p>}
              {demand.data && !demand.loading && (
                <div className="flex items-center justify-between p-4 rounded-lg bg-slate-800/50 border border-slate-700 mt-2">
                  <div>
                    <p className="text-xs text-slate-500 uppercase tracking-widest">Demanda próxima semana</p>
                    <p className="font-mono text-3xl font-semibold text-cyan-400 mt-1">
                      {demand.data.demanda_proxima_semana} <span className="text-base text-slate-400 font-normal">uds</span>
                    </p>
                  </div>
                  <AlertBadge variant="info">SKU: {demand.data.producto_cod}</AlertBadge>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Mini bar chart of mock risk distribution until dedicated endpoint available */}
        <ChartCard title="Distribución de Riesgo de Stock" badge={{ label: 'Inventario', variant: 'hist' }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={[
                { estado: 'Crítico',   total: MOCK_ALERTS.filter(a => a.estado === 'critical').length },
                { estado: 'Moderado',  total: MOCK_ALERTS.filter(a => a.estado === 'warning').length },
                { estado: 'Normal',    total: MOCK_ALERTS.filter(a => a.estado === 'neutral').length },
              ]}
              margin={{ top: 4, right: 10, left: -20, bottom: 4 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
              <XAxis dataKey="estado" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip
                cursor={{ fill: '#1e293b' }}
                contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: '8px', fontSize: '12px' }}
              />
              <Bar dataKey="total" radius={[4, 4, 0, 0]} barSize={36}
                fill="#06b6d4"
              />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Alertas de Reposición */}
      <div className="card animate-fade-in-up stagger-2 overflow-hidden">
        <div className="p-6 border-b border-slate-800 flex items-center justify-between">
          <h3 className="font-sans font-semibold text-slate-200">Alertas Inteligentes de Reposición (ML)</h3>
          <AlertBadge variant="warning">{MOCK_ALERTS.filter(a => a.estado !== 'neutral').length} ítems</AlertBadge>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm whitespace-nowrap">
            <thead className="bg-slate-950/60 text-slate-500 text-xs uppercase tracking-widest">
              <tr>
                <th className="px-6 py-4">SKU / Producto</th>
                <th className="px-6 py-4">Stock Actual</th>
                <th className="px-6 py-4 text-cyan-400">Demanda Prevista</th>
                <th className="px-6 py-4">Punto Reorden</th>
                <th className="px-6 py-4">Estado</th>
                <th className="px-6 py-4">Acción</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/80">
              {MOCK_ALERTS.map((row) => (
                <tr key={row.sku} className="hover:bg-slate-800/20 transition-colors">
                  <td className="px-6 py-4">
                    <p className="font-semibold text-slate-200">{row.sku}</p>
                    <p className="text-xs text-slate-500">{row.name}</p>
                  </td>
                  <td className="px-6 py-4 font-mono">
                    {row.stock === 0 ? (
                      <span className="text-red-400 bg-red-500/10 px-2 py-0.5 rounded text-xs">0 — Agotado</span>
                    ) : (
                      <span className="text-slate-300">{row.stock}</span>
                    )}
                  </td>
                  <td className="px-6 py-4 font-mono text-cyan-400">{row.demanda} uds</td>
                  <td className="px-6 py-4 font-mono text-slate-400">{row.reorden} uds</td>
                  <td className="px-6 py-4">
                    <AlertBadge variant={row.estado as 'critical' | 'warning' | 'neutral'}>
                      {row.estado === 'critical' ? 'Crítico' : row.estado === 'warning' ? 'Moderado' : 'Normal'}
                    </AlertBadge>
                  </td>
                  <td className="px-6 py-4">
                    {isAdmin ? (
                      <button className="px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white rounded text-xs font-semibold glow-accent-sm transition-colors">
                        Solicitar Traspaso
                      </button>
                    ) : (
                      <span className="text-xs text-slate-500 italic block mt-1">🔒 Operación bloqueada (Solo Admin)</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
