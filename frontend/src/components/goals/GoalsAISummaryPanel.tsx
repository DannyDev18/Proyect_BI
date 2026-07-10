import { AlertTriangle, TrendingUp, Sparkles } from 'lucide-react';
import { useGoalsAISummary } from '../../hooks/goals';
import { ChartCard } from '../ui/ChartCard';
import { AlertBadge } from '../ui/AlertBadge';
import { fmt, pct } from '../../utils/format';

export function GoalsAISummaryPanel() {
  const { data, loading, error } = useGoalsAISummary();

  if (error) {
    return <div className="card p-4 text-red-400 text-sm">{error}</div>;
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <ChartCard title="Vendedores en riesgo" badge={{ label: 'IA', variant: 'ml' }} loading={loading}>
        {data.vendedores_en_riesgo.length === 0 ? (
          <p className="text-slate-500 text-sm text-center mt-6">Ningún vendedor por debajo del ritmo esperado.</p>
        ) : (
          <ul className="space-y-2 overflow-auto max-h-[260px]">
            {data.vendedores_en_riesgo.map((v, i) => (
              <li key={i} className="flex justify-between items-center py-2 border-b border-slate-800 last:border-0">
                <div>
                  <p className="text-sm font-medium text-slate-200 flex items-center gap-1.5">
                    <AlertTriangle size={13} className="text-red-400" /> {v.nombre}
                  </p>
                  <p className="text-xs text-slate-500">{fmt(v.ventas)} / {fmt(v.meta)}</p>
                </div>
                <AlertBadge variant="critical">{pct(v.pct_cumplimiento)} vs {pct(v.pct_esperado_a_la_fecha)} esperado</AlertBadge>
              </li>
            ))}
          </ul>
        )}
      </ChartCard>

      <ChartCard title="Alta probabilidad de superar la meta" badge={{ label: 'IA', variant: 'ml' }} loading={loading}>
        {data.vendedores_alta_probabilidad.length === 0 ? (
          <p className="text-slate-500 text-sm text-center mt-6">Ningún vendedor destaca sobre el ritmo esperado todavía.</p>
        ) : (
          <ul className="space-y-2 overflow-auto max-h-[260px]">
            {data.vendedores_alta_probabilidad.map((v, i) => (
              <li key={i} className="flex justify-between items-center py-2 border-b border-slate-800 last:border-0">
                <div>
                  <p className="text-sm font-medium text-slate-200 flex items-center gap-1.5">
                    <TrendingUp size={13} className="text-green-400" /> {v.nombre}
                  </p>
                  <p className="text-xs text-slate-500">{fmt(v.ventas)} / {fmt(v.meta)}</p>
                </div>
                <AlertBadge variant="success">{pct(v.pct_cumplimiento)} vs {pct(v.pct_esperado_a_la_fecha)} esperado</AlertBadge>
              </li>
            ))}
          </ul>
        )}
      </ChartCard>

      <ChartCard title="Recomendaciones comerciales por categoría" badge={{ label: 'Reglas Asociación', variant: 'ml' }} loading={loading}>
        {data.recomendaciones_por_categoria.length === 0 ? (
          <p className="text-slate-500 text-sm text-center mt-6">Sin reglas de asociación disponibles.</p>
        ) : (
          <ul className="space-y-2 overflow-auto max-h-[260px]">
            {data.recomendaciones_por_categoria.map((r, i) => (
              <li key={i} className="flex justify-between items-center py-2 border-b border-slate-800 last:border-0">
                <div>
                  <p className="text-sm font-medium text-slate-200 flex items-center gap-1.5">
                    <Sparkles size={13} className="text-amber-400" /> {r.categoria_origen} → {r.categoria_sugerida}
                  </p>
                  <p className="text-xs text-slate-500 font-mono">{r.producto_sugerido}</p>
                </div>
                <AlertBadge variant="info">lift {r.score_afinidad.toFixed(1)}</AlertBadge>
              </li>
            ))}
          </ul>
        )}
      </ChartCard>
    </div>
  );
}
