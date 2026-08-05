import { useState } from 'react';
import { Settings2 } from 'lucide-react';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { usePoliticaABC, useUpdatePoliticaABC } from '../../hooks/replenishment';

/** Vista hija "Configuración" del módulo de Inventario/Reabastecimiento (Fase 6,
 * docs/features/plan_modulo_inventario_reabastecimiento.md), solo gerencia/
 * administrador: política de nivel de servicio por clase ABC. El lead time por
 * producto/categoría/proveedor se administra vía API (sin UI dedicada en este corte --
 * F4 del plan original priorizó la lista priorizada sobre la administración fina de
 * lead times, que hoy tiene un default global razonable). */
export const ReplenishmentPoliticaPanel = () => {
  const politica = usePoliticaABC();
  const update = useUpdatePoliticaABC();
  const [editando, setEditando] = useState<Record<string, string>>({});

  if (politica.loading) return null;
  if (politica.error || !politica.data) return null;

  return (
    <div className="card p-4 animate-fade-in-up">
      <div className="flex items-center gap-2 mb-3">
        <Settings2 size={16} className="text-slate-400" />
        <h3 className="font-sans font-semibold text-slate-200 text-sm">Política de nivel de servicio por clase ABC</h3>
      </div>
      <div className="flex flex-wrap gap-4">
        {politica.data.map((p) => {
          const valor = editando[p.clase_abc] ?? String(p.nivel_servicio);
          return (
            <div key={p.clase_abc} className="flex items-center gap-2">
              <Badge variant="neutral">Clase {p.clase_abc}</Badge>
              <input
                type="number" min={0.5} max={0.999} step={0.001}
                value={valor}
                onChange={(e) => setEditando((s) => ({ ...s, [p.clase_abc]: e.target.value }))}
                className="w-24 bg-slate-950 border border-slate-700 rounded-md px-2 py-1 text-xs text-slate-200 outline-none focus-ring"
              />
              <Button
                size="sm" variant="ghost"
                disabled={update.loading}
                onClick={() => {
                  const n = Number(valor);
                  if (!isNaN(n) && n > 0 && n < 1) update.mutate({ claseAbc: p.clase_abc, nivelServicio: n });
                }}
              >
                Guardar
              </Button>
            </div>
          );
        })}
      </div>
      {update.error && <p className="text-xs text-danger mt-2">{update.error}</p>}
      <p className="text-[11px] text-slate-500 mt-2">
        Nivel de servicio objetivo (0-1) usado para calcular el stock de seguridad (fórmula z × σ × √LT) de cada clase.
      </p>
    </div>
  );
};
