import { useState } from 'react';
import { FlaskConical } from 'lucide-react';
import { Button } from '../ui/Button';
import { useSimularReabastecimiento } from '../../hooks/replenishment';
import type { toQueryFilters } from '../../store/bodegaFiltersStore';
import { fmt } from '../../utils/format';

interface ReplenishmentSimuladorPanelProps {
  filters: ReturnType<typeof toQueryFilters>;
}

/** F8 (§6.4/§7.1, bloque 4 Simulación): vista hija "Simulador what-if" del módulo de
 * Inventario/Reabastecimiento (Fase 6, docs/features/plan_modulo_inventario_
 * reabastecimiento.md) -- de solo lectura, nunca persiste, solo compara el resumen
 * actual contra uno hipotético bajo lead time/nivel de servicio distintos. */
export const ReplenishmentSimuladorPanel = ({ filters }: ReplenishmentSimuladorPanelProps) => {
  const { data, loading, error, simular } = useSimularReabastecimiento();
  const [horizonteDias, setHorizonteDias] = useState(30);
  const [leadTime, setLeadTime] = useState('');
  const [nivelA, setNivelA] = useState('');
  const [nivelB, setNivelB] = useState('');
  const [nivelC, setNivelC] = useState('');

  const ejecutar = () => {
    const niveles: Record<string, number> = {};
    if (nivelA) niveles.A = Number(nivelA);
    if (nivelB) niveles.B = Number(nivelB);
    if (nivelC) niveles.C = Number(nivelC);
    simular({
      almacen: filters.almacen, categoria: filters.categoria, proveedor: filters.proveedor,
      tipo_movimiento: filters.tipo_movimiento, horizonte_dias: horizonteDias,
      lead_time_default_dias: leadTime ? Number(leadTime) : null,
      niveles_servicio: Object.keys(niveles).length > 0 ? niveles : null,
    });
  };

  return (
    <div className="card p-4 animate-fade-in-up">
      <div className="flex items-center gap-2 mb-3">
        <FlaskConical size={16} className="text-slate-400" />
        <h3 className="font-sans font-semibold text-slate-200 text-sm">Simulador what-if</h3>
        <span className="text-[11px] text-slate-500">-- no guarda nada, solo compara</span>
      </div>
      <div className="flex flex-wrap items-end gap-3 mb-3">
        <div className="flex flex-col gap-1">
          <label className="text-[11px] uppercase tracking-widest text-slate-500">Horizonte (días)</label>
          <input
            type="number" min={1} value={horizonteDias}
            onChange={(e) => setHorizonteDias(Number(e.target.value) || 30)}
            className="w-24 bg-slate-950 border border-slate-700 rounded-md px-2 py-1 text-xs text-slate-200 outline-none focus-ring"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-[11px] uppercase tracking-widest text-slate-500">Lead time global (días)</label>
          <input
            type="number" min={1} placeholder="ej. 30" value={leadTime}
            onChange={(e) => setLeadTime(e.target.value)}
            className="w-28 bg-slate-950 border border-slate-700 rounded-md px-2 py-1 text-xs text-slate-200 outline-none focus-ring"
          />
        </div>
        {(['A', 'B', 'C'] as const).map((clase) => (
          <div key={clase} className="flex flex-col gap-1">
            <label className="text-[11px] uppercase tracking-widest text-slate-500">Nivel servicio {clase}</label>
            <input
              type="number" min={0.5} max={0.999} step={0.001} placeholder="ej. 0.99"
              value={clase === 'A' ? nivelA : clase === 'B' ? nivelB : nivelC}
              onChange={(e) => (clase === 'A' ? setNivelA : clase === 'B' ? setNivelB : setNivelC)(e.target.value)}
              className="w-24 bg-slate-950 border border-slate-700 rounded-md px-2 py-1 text-xs text-slate-200 outline-none focus-ring"
            />
          </div>
        ))}
        <Button size="sm" onClick={ejecutar} loading={loading}>Simular</Button>
      </div>
      {error && <p className="text-xs text-danger">{error}</p>}
      {data && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div className="border border-slate-800 rounded-lg p-2">
            <p className="text-slate-500">Riesgo crítico</p>
            <p className="font-mono text-slate-300">
              {data.resumen_actual.productos_riesgo_critico} → <span className="text-warning font-semibold">{data.resumen_simulado.productos_riesgo_critico}</span>
            </p>
          </div>
          <div className="border border-slate-800 rounded-lg p-2">
            <p className="text-slate-500">Riesgo alto</p>
            <p className="font-mono text-slate-300">
              {data.resumen_actual.productos_riesgo_alto} → <span className="text-warning font-semibold">{data.resumen_simulado.productos_riesgo_alto}</span>
            </p>
          </div>
          <div className="border border-slate-800 rounded-lg p-2">
            <p className="text-slate-500">Con recomendación</p>
            <p className="font-mono text-slate-300">
              {data.resumen_actual.productos_con_recomendacion_compra} → <span className="text-warning font-semibold">{data.resumen_simulado.productos_con_recomendacion_compra}</span>
            </p>
          </div>
          <div className="border border-slate-800 rounded-lg p-2">
            <p className="text-slate-500">Costo de compra sugerida</p>
            <p className="font-mono text-slate-300">
              {fmt(data.resumen_actual.costo_total_compra_sugerida)} → <span className="text-warning font-semibold">{fmt(data.resumen_simulado.costo_total_compra_sugerida)}</span>
            </p>
          </div>
        </div>
      )}
    </div>
  );
};
