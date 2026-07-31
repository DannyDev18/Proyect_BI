import { CalendarClock, CalendarCheck } from 'lucide-react';
import { EmptyState } from '../ui/EmptyState';
import { ErrorState } from '../ui/ErrorState';
import { Badge } from '../ui/Badge';
import { useProximasAcciones } from '../../hooks/cartera360';
import type { EstadoProximaAccion } from '../../types/cartera360';

interface UpcomingActionsProps {
  onSelect: (clienteId: string) => void;
}

const ESTADO_BADGE: Record<EstadoProximaAccion, { label: string; variant: 'danger' | 'warning' | 'info' }> = {
  vencida: { label: 'Vencida', variant: 'danger' },
  hoy: { label: 'Hoy', variant: 'warning' },
  proxima: { label: 'Próxima', variant: 'info' },
};

/** Próximas acciones (§4.7 del plan, "próxima acción" capturada en el registro de
 * gestión): agenda concreta de seguimientos que TÚ mismo programaste, ordenada por
 * fecha.
 *
 * Auditoría 43 (H43-13, docs/auditoria/43_correcciones_sesion_ventas_y_datos.md):
 * ANTES este panel filtraba `proxima_accion_fecha` sobre los clientes de `/ruta/hoy` --
 * pero ese ranking EXCLUYE deliberadamente a todo cliente con una fecha futura (rotación
 * de la ruta), así que el panel casi nunca tenía contenido: la lista que lo alimentaba
 * era el complemento exacto de lo que debía mostrar. Ahora consume su propio endpoint
 * (`GET /ruta/proximas-acciones`), independiente del top-N del día. */
export const UpcomingActions = ({ onSelect }: UpcomingActionsProps) => {
  const { data, loading, error, refetch } = useProximasAcciones();

  if (loading) {
    return <p className="text-sm text-slate-500 animate-pulse-slow">Cargando agenda…</p>;
  }
  if (error) {
    return <ErrorState message={error} onRetry={refetch} />;
  }

  const acciones = data?.acciones ?? [];
  if (acciones.length === 0) {
    return (
      <EmptyState
        icon={CalendarCheck}
        title="Sin próximas acciones programadas"
        description="Cuando registres una gestión con fecha de seguimiento, aparecerá aquí."
      />
    );
  }

  return (
    <ul className="space-y-2">
      {acciones.map((a) => {
        const badge = ESTADO_BADGE[a.estado];
        return (
          <li key={a.cliente_id}>
            <button
              type="button"
              onClick={() => onSelect(a.cliente_id)}
              className="w-full flex items-center gap-3 text-left rounded-lg border border-slate-800 bg-slate-800/30 px-3 py-2.5 hover:border-primary/40 focus-ring transition-colors"
            >
              <CalendarClock size={16} className="text-warning shrink-0" />
              <span className="min-w-0 flex-1 truncate text-sm text-slate-300">{a.nombre_cliente}</span>
              <Badge variant={badge.variant}>{badge.label}</Badge>
              <span className="text-xs font-mono text-slate-500 shrink-0">{a.proxima_accion_fecha}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
};
