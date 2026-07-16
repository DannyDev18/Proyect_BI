import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, PackageSearch } from 'lucide-react';
import {
  Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { ChartCard } from '../ui/ChartCard';
import { usePrediccionComprasMes } from '../../hooks/bodega';
import { fmt } from '../../utils/format';
import { chartTheme } from '../../utils/chartTheme';
import type { BodegaQueryFilters } from '../../services/bodega';

const tooltipStyle = {
  backgroundColor: chartTheme.cardBg, borderColor: chartTheme.grid, borderRadius: '8px', fontSize: '12px',
} as const;

interface PrediccionComprasChartProps {
  filters: BodegaQueryFilters;
}

/** Predicción de compras del próximo mes calendario, enlazada al filtro global de
 * categoría (§1.1), con drill-down a los 20 artículos con más ventas de la categoría
 * (docs/auditoria/24_prediccion_categoria_paginacion.md). */
export const PrediccionComprasChart = ({ filters }: PrediccionComprasChartProps) => {
  const [productoCod, setProductoCod] = useState<string | null>(null);
  const prediccion = usePrediccionComprasMes(filters, productoCod);

  // Volver a la vista de categoría si el usuario cambia de categoría en el filtro global.
  useEffect(() => { setProductoCod(null); }, [filters.categoria]);

  const serie = useMemo(
    () => (prediccion.data?.serie ?? []).map((p) => ({
      fecha: p.fecha, unidades: p.unidades, banda: [p.banda_inferior, p.banda_superior] as [number, number],
    })),
    [prediccion.data],
  );

  const articuloActivo = productoCod
    ? prediccion.data?.top_articulos.find((a) => a.codart === productoCod)
    : null;

  return (
    <ChartCard
      title="Predicción de Compras — Próximo Mes"
      badge={{
        label: prediccion.data?.metodo === 'ml_demand_rf' ? 'ML demand_rf' : 'Proyección estadística',
        variant: 'ml',
      }}
      height="h-[560px]"
      loading={prediccion.loading}
      actions={
        <div className="flex items-center gap-3 text-xs text-slate-400">
          {productoCod && (
            <button
              onClick={() => setProductoCod(null)}
              className="flex items-center gap-1 text-primary hover:underline cursor-pointer focus-ring rounded"
            >
              <ArrowLeft size={12} /> Volver a la categoría
            </button>
          )}
          {prediccion.data && (
            <span className="font-mono">{prediccion.data.mes_objetivo}</span>
          )}
        </div>
      }
    >
      <div className="h-full flex flex-col gap-4">
        {prediccion.data && (
          <div className="flex flex-wrap gap-4 text-xs text-slate-400">
            {articuloActivo ? (
              <>
                <span className="text-slate-200 font-semibold">{articuloActivo.nombre}</span>
                <span>Predicción del mes: <span className="font-mono text-info">{articuloActivo.prediccion_mes.toLocaleString('es-EC')} uds</span></span>
                <span>Compra sugerida: <span className="font-mono text-warning">{articuloActivo.compra_sugerida.toLocaleString('es-EC')} uds</span></span>
                <span>Stock actual: <span className="font-mono">{articuloActivo.stock_actual.toLocaleString('es-EC')}</span></span>
              </>
            ) : (
              <>
                <span>Unidades previstas: <span className="font-mono text-info">{prediccion.data.resumen.unidades_previstas_mes.toLocaleString('es-EC')}</span></span>
                <span>Costo estimado de compra: <span className="font-mono text-warning">{fmt(prediccion.data.resumen.costo_estimado_compra)}</span></span>
                <span>{prediccion.data.resumen.productos_incluidos} artículos incluidos</span>
              </>
            )}
          </div>
        )}

        <div className="flex-1 min-h-[160px]">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={serie} margin={{ top: 4, right: 16, left: -10, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} vertical={false} />
              <XAxis dataKey="fecha" tick={{ fill: chartTheme.axis, fontSize: 10 }} tickFormatter={(f: string) => f.slice(8)} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: chartTheme.axis, fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={tooltipStyle} />
              <Area dataKey="banda" name="Banda de confianza" stroke="none" fill={chartTheme.ml} fillOpacity={0.15} connectNulls />
              <Line dataKey="unidades" name="Predicción (unidades)" stroke={chartTheme.ml} strokeWidth={2} dot={false} connectNulls />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        {!productoCod && (
          <div className="border-t border-slate-800 pt-3">
            <p className="text-xs text-slate-500 mb-2 flex items-center gap-1.5">
              <PackageSearch size={12} /> Top 20 artículos con más ventas de la categoría — clic para ver su predicción individual
            </p>
            <div className="overflow-x-auto max-h-[160px] overflow-y-auto">
              <table className="w-full text-left text-xs whitespace-nowrap">
                <thead className="text-slate-500 uppercase tracking-widest sticky top-0 bg-slate-900">
                  <tr>
                    <th className="py-1.5 pr-4">Artículo</th>
                    <th className="py-1.5 pr-4 text-right">Ventas período</th>
                    <th className="py-1.5 pr-4 text-right">Predicción mes</th>
                    <th className="py-1.5 pr-4 text-right">Compra sugerida</th>
                    <th className="py-1.5">Método</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {(prediccion.data?.top_articulos ?? []).map((a) => (
                    <tr
                      key={a.codart}
                      onClick={() => setProductoCod(a.codart)}
                      onKeyDown={(e) => { if (e.key === 'Enter') setProductoCod(a.codart); }}
                      tabIndex={0}
                      role="button"
                      aria-label={`Ver predicción individual de ${a.nombre}`}
                      className="hover:bg-slate-800/30 cursor-pointer transition-colors focus-ring"
                    >
                      <td className="py-1.5 pr-4">
                        <span className="text-slate-200">{a.nombre}</span>
                        <span className="text-slate-500"> · {a.codart}</span>
                      </td>
                      <td className="py-1.5 pr-4 text-right font-mono text-slate-300">{a.unidades_vendidas_periodo.toLocaleString('es-EC')}</td>
                      <td className="py-1.5 pr-4 text-right font-mono text-info">{a.prediccion_mes.toLocaleString('es-EC')}</td>
                      <td className="py-1.5 pr-4 text-right font-mono text-warning">{a.compra_sugerida.toLocaleString('es-EC')}</td>
                      <td className="py-1.5 text-slate-500">{a.metodo === 'ml_demand_rf' ? 'ML' : 'Estadístico'}</td>
                    </tr>
                  ))}
                  {prediccion.data && prediccion.data.top_articulos.length === 0 && (
                    <tr><td colSpan={5} className="py-4 text-slate-500">Sin ventas registradas para esta categoría en el período.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </ChartCard>
  );
};
