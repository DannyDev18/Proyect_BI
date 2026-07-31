import { ShoppingCart, Undo2, Banknote, MessageSquare, History } from 'lucide-react';
import { EmptyState } from '../ui/EmptyState';
import { ErrorState } from '../ui/ErrorState';
import { useTimelineCliente } from '../../hooks/cartera360';
import type { TipoEventoTimeline } from '../../types/cartera360';

const money = (n: number) => n.toLocaleString('es-EC', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 });

const ICONS: Record<TipoEventoTimeline, typeof ShoppingCart> = {
  compra: ShoppingCart,
  devolucion: Undo2,
  cobro: Banknote,
  gestion: MessageSquare,
};

const COLORS: Record<TipoEventoTimeline, string> = {
  compra: 'text-success bg-success/10 border-success/20',
  devolucion: 'text-danger bg-danger/10 border-danger/20',
  cobro: 'text-info bg-info/10 border-info/20',
  gestion: 'text-primary bg-primary/10 border-primary/20',
};

/** Timeline real del cliente (§4.6): compras/devoluciones/cobros del EDW + gestiones
 * registradas. Poblado desde el día 1 aunque no haya ninguna gestión (D-1) -- los
 * eventos reales del EDW ya le dan contenido, mismo diseño documentado en el plan
 * para que el módulo no se vea vacío en la primera semana de uso. */
export const ClientTimeline = ({ clienteId }: { clienteId: string }) => {
  const { data, loading, error, refetch } = useTimelineCliente(clienteId);

  if (loading) {
    return (
      <div className="space-y-3">
        {[0, 1, 2].map((i) => <div key={i} className="skeleton h-14 rounded-lg" />)}
      </div>
    );
  }
  if (error) return <ErrorState message={error} onRetry={refetch} />;
  if (!data || data.eventos.length === 0) {
    return (
      <EmptyState
        icon={History}
        title="Sin eventos registrados"
        description="No hay compras, devoluciones, cobros ni gestiones para este cliente todavía."
      />
    );
  }

  return (
    <ol className="space-y-3">
      {data.eventos.map((ev, i) => {
        const Icon = ICONS[ev.tipo];
        return (
          <li key={`${ev.tipo}-${ev.fecha}-${i}`} className="flex gap-3">
            <div className={`shrink-0 p-1.5 rounded-lg border h-fit ${COLORS[ev.tipo]}`}>
              <Icon size={14} />
            </div>
            <div className="min-w-0 flex-1 pb-3 border-b border-slate-800/60">
              <div className="flex items-baseline justify-between gap-2">
                <p className="text-sm text-slate-300 truncate">{ev.descripcion}</p>
                {ev.monto !== null && <span className="text-xs font-mono text-slate-500 shrink-0">{money(ev.monto)}</span>}
              </div>
              <p className="text-[11px] text-slate-600 mt-0.5">{ev.fecha}</p>
            </div>
          </li>
        );
      })}
    </ol>
  );
};
