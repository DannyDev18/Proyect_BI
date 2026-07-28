import type { LucideIcon } from 'lucide-react';
import { Info, ShoppingCart, TrendingUp, Wallet } from 'lucide-react';
import { ErrorState } from '../ui/ErrorState';
import { useSimularVenta } from '../../hooks/crossSelling';
import { fmtMoney } from '../../utils/format';

const Metrica = ({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: string }) => (
  <div className="flex items-center gap-2.5">
    <div className="p-2 rounded-lg bg-slate-800/60 border border-slate-800">
      <Icon size={14} className="text-primary" />
    </div>
    <div>
      <p className="text-[11px] uppercase tracking-widest text-slate-500">{label}</p>
      <p className="font-mono text-sm text-slate-200">{value}</p>
    </div>
  </div>
);

interface SimulacionPanelProps {
  items: string[];
  clienteId: string | null;
}

/** Fase 3 de docs/features/plan_refactor_venta_cruzada_ia.md (CAMBIO 4/12): cifras
 * REALES de la canasta que el vendedor está armando -- ticket/margen salen del
 * catálogo vigente, sin cálculo especulativo. Recalcula en vivo (debounced, ver
 * `useSimularVenta`) con cada cambio de canasta. */
export const SimulacionPanel = ({ items, clienteId }: SimulacionPanelProps) => {
  const simulacion = useSimularVenta(items, clienteId);

  if (simulacion.loading && !simulacion.data) {
    return (
      <div className="pt-4 border-t border-slate-800 space-y-3">
        <div className="skeleton h-3 w-40 rounded" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-10 rounded-lg" />)}
        </div>
      </div>
    );
  }

  if (simulacion.error) {
    return (
      <div className="pt-4 border-t border-slate-800">
        <ErrorState message={simulacion.error} onRetry={simulacion.refetch} />
      </div>
    );
  }

  const s = simulacion.data;
  if (!s) return null;

  return (
    <div className="pt-4 border-t border-slate-800 space-y-3">
      <p className="text-[11px] uppercase tracking-widest text-slate-500">Resumen de la canasta</p>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Metrica icon={ShoppingCart} label="Ticket estimado" value={fmtMoney(s.ticket_estimado)} />
        <Metrica icon={Wallet} label="Margen estimado" value={s.margen_estimado != null ? fmtMoney(s.margen_estimado) : 'No disponible'} />
        {s.incremento_vs_ticket_promedio_cliente != null && (
          <Metrica
            icon={TrendingUp}
            label="Vs. ticket promedio"
            value={`${s.incremento_vs_ticket_promedio_cliente >= 0 ? '+' : ''}${fmtMoney(s.incremento_vs_ticket_promedio_cliente)}`}
          />
        )}
        {s.probabilidad_recompra != null && (
          <Metrica icon={TrendingUp} label="Prob. de recompra" value={`${s.probabilidad_recompra.toFixed(0)}%`} />
        )}
      </div>
      <p className="text-xs text-slate-500 flex items-start gap-1.5">
        <Info size={13} className="shrink-0 mt-0.5" />
        {s.explicacion}
      </p>
    </div>
  );
};
