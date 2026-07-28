import { useState } from 'react';
import { ChevronDown, ChevronUp, HelpCircle } from 'lucide-react';
import { ErrorState } from '../ui/ErrorState';
import { useExplicacionChurn } from '../../hooks/crossSelling';

const NOMBRES_FEATURE: Record<string, string> = {
  recency: 'Días desde la última compra',
  frequency: 'Frecuencia de compra',
  monetary_value: 'Valor total comprado',
  average_ticket: 'Ticket promedio',
};

/** Fase 6 de docs/features/plan_refactor_venta_cruzada_ia.md (§2.1 Opción A):
 * "¿Por qué esto?" -- explicabilidad REAL (SHAP), etiquetada explícitamente como
 * "Explicación del modelo", nunca "IA generativa" (R-3 del plan: no fingir IA
 * generativa donde hay reglas/cálculos deterministas). Colapsado por defecto: la
 * consulta SHAP solo se dispara al expandir (`useExplicacionChurn` con `enabled`). */
export const WhyExplanationPanel = ({ clienteId }: { clienteId: string }) => {
  const [abierto, setAbierto] = useState(false);
  const explicacion = useExplicacionChurn(clienteId, abierto);

  const maxAbs = Math.max(1e-6, ...(explicacion.data?.contribuciones.map((c) => Math.abs(c.contribucion)) ?? [0]));

  return (
    <div className="mt-4 pt-4 border-t border-slate-800">
      <button
        onClick={() => setAbierto((v) => !v)}
        className="flex items-center gap-1.5 text-xs font-semibold text-slate-400 hover:text-slate-200 transition-colors"
      >
        <HelpCircle size={13} /> ¿Por qué este riesgo de abandono?
        {abierto ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
      </button>

      {abierto && (
        <div className="mt-3">
          <p className="text-[10px] uppercase tracking-widest text-slate-600 mb-2">Explicación del modelo (SHAP)</p>
          {explicacion.loading ? (
            <div className="space-y-2">
              {[0, 1, 2].map((i) => <div key={i} className="skeleton h-5 rounded" />)}
            </div>
          ) : explicacion.error ? (
            <ErrorState message={explicacion.error} onRetry={explicacion.refetch} className="py-4" />
          ) : explicacion.data && explicacion.data.contribuciones.length > 0 ? (
            <div className="space-y-2">
              {explicacion.data.contribuciones.map((c) => {
                const empujaAbandono = c.contribucion > 0;
                const pct = (Math.abs(c.contribucion) / maxAbs) * 100;
                return (
                  <div key={c.feature} className="text-xs">
                    <div className="flex justify-between text-slate-400 mb-0.5">
                      <span>{NOMBRES_FEATURE[c.feature] ?? c.feature}</span>
                      <span className="font-mono text-slate-500">{c.valor.toLocaleString('es-EC', { maximumFractionDigits: 1 })}</span>
                    </div>
                    <div className="h-1.5 rounded-full bg-slate-800/80 overflow-hidden">
                      <div
                        className={`h-full rounded-full ${empujaAbandono ? 'bg-danger' : 'bg-success'}`}
                        style={{ width: `${pct}%` }}
                        title={`${empujaAbandono ? 'Aumenta' : 'Reduce'} la probabilidad de abandono (contribución SHAP: ${c.contribucion.toFixed(4)})`}
                      />
                    </div>
                  </div>
                );
              })}
              <p className="text-[11px] text-slate-600 mt-2">
                <span className="text-danger">■</span> aumenta el riesgo de abandono ·{' '}
                <span className="text-success">■</span> lo reduce
              </p>
            </div>
          ) : (
            <p className="text-xs text-slate-500">No hay suficiente historial para explicar el riesgo de este cliente.</p>
          )}
        </div>
      )}
    </div>
  );
};
