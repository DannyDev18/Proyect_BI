import { useState } from 'react';
import { CheckCircle2, ClipboardList, XCircle } from 'lucide-react';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { useCrearPropuestaCompra, useDecidirPropuestaCompra, usePropuestasCompra } from '../../hooks/replenishment';
import type { toQueryFilters } from '../../store/bodegaFiltersStore';
import { fmtMoney } from '../../utils/format';
import type { EstadoPropuestaCompra } from '../../types/replenishment';

const estadoPropuestaBadge: Record<EstadoPropuestaCompra, 'neutral' | 'success' | 'danger' | 'info'> = {
  borrador: 'neutral', aprobada: 'success', rechazada: 'danger', exportada: 'info',
};

interface ReplenishmentPropuestasPanelProps {
  filters: ReturnType<typeof toQueryFilters>;
}

/** F9 (§6.3/§8, bloque 5 Gestión Operativa): vista hija "Propuestas de compra" del
 * módulo de Inventario/Reabastecimiento (Fase 6, docs/features/plan_modulo_inventario_
 * reabastecimiento.md). "Generar propuesta" congela un snapshot de la Lista Inteligente
 * actual (solo las filas con cantidad sugerida > 0 y riesgo crítico/alto, bajo los
 * filtros globales vigentes); aprobar/rechazar es una decisión real y auditable, no un
 * `useState` que se pierde al recargar la página (a diferencia de la aprobación de
 * transferencias en `/bodega/almacenes`, H-5 del plan, que queda fuera de este corte --
 * ver auditoría 50). */
export const ReplenishmentPropuestasPanel = ({ filters }: ReplenishmentPropuestasPanelProps) => {
  const [horizonteDias] = useState(30);
  const propuestas = usePropuestasCompra();
  const crear = useCrearPropuestaCompra();
  const decidir = useDecidirPropuestaCompra();

  return (
    <div className="card p-4 animate-fade-in-up">
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-2">
          <ClipboardList size={16} className="text-slate-400" />
          <h3 className="font-sans font-semibold text-slate-200 text-sm">Propuestas de compra</h3>
        </div>
        <Button
          size="sm"
          loading={crear.loading}
          onClick={() => crear.crear({
            almacen: filters.almacen, categoria: filters.categoria, proveedor: filters.proveedor,
            tipo_movimiento: filters.tipo_movimiento, horizonte_dias: horizonteDias, solo_criticos: true,
          })}
        >
          Generar propuesta (críticos, filtros actuales)
        </Button>
      </div>
      {crear.error && <p className="text-xs text-danger mb-2">{crear.error}</p>}
      {decidir.error && <p className="text-xs text-danger mb-2">{decidir.error}</p>}

      {propuestas.loading && <p className="text-xs text-slate-500">Cargando…</p>}
      {!propuestas.loading && (propuestas.data ?? []).length === 0 && (
        <p className="text-xs text-slate-500">Sin propuestas generadas todavía.</p>
      )}
      {!propuestas.loading && (propuestas.data?.length ?? 0) > 0 && (
        <ul className="space-y-2">
          {propuestas.data!.map((p) => (
            <li key={p.id} className="flex items-center justify-between gap-3 text-xs border border-slate-800 rounded-lg p-2.5">
              <div>
                <span className="font-mono text-slate-300">#{p.id}</span>{' '}
                <Badge variant={estadoPropuestaBadge[p.estado]}>{p.estado}</Badge>{' '}
                <span className="text-slate-400">{fmtMoney(p.total)} · horizonte {p.horizonte_dias}d</span>
                <p className="text-slate-600">{new Date(p.creado_en).toLocaleString('es-EC')}</p>
              </div>
              {p.estado === 'borrador' && (
                <div className="flex items-center gap-1.5">
                  <button
                    type="button" onClick={() => decidir.mutate({ id: p.id, decision: 'aprobar' })}
                    aria-label="Aprobar propuesta" title="Aprobar"
                    className="p-1.5 rounded-md transition-colors cursor-pointer focus-ring text-slate-500 hover:text-success"
                  >
                    <CheckCircle2 size={16} />
                  </button>
                  <button
                    type="button" onClick={() => decidir.mutate({ id: p.id, decision: 'rechazar' })}
                    aria-label="Rechazar propuesta" title="Rechazar"
                    className="p-1.5 rounded-md transition-colors cursor-pointer focus-ring text-slate-500 hover:text-danger"
                  >
                    <XCircle size={16} />
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
