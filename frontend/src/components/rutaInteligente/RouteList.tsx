import { CheckCircle2 } from 'lucide-react';
import { EmptyState } from '../ui/EmptyState';
import { ErrorState } from '../ui/ErrorState';
import { PriorityCard } from './PriorityCard';
import type { ClienteRuta } from '../../types/cartera360';

interface RouteListProps {
  clientes: ClienteRuta[];
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onSelect: (clienteId: string) => void;
}

/** Lista de la ruta del día (§4.3): hasta 10 clientes (criterio de aceptación 1 del
 * plan, "≤10 clientes priorizados, sin scroll ni filtros previos") -- ya viene acotada
 * por el backend (`CARTERA360_RUTA_TOP_N`), así que a diferencia de la tabla completa
 * de `/cartera360` (hasta 100 filas) esta lista NO necesita virtualización. */
export const RouteList = ({ clientes, loading, error, onRetry, onSelect }: RouteListProps) => {
  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {Array.from({ length: 6 }).map((_, i) => <div key={i} className="skeleton h-48 rounded-xl" />)}
      </div>
    );
  }
  if (error) return <ErrorState message={error} onRetry={onRetry} />;
  if (clientes.length === 0) {
    return (
      <EmptyState
        icon={CheckCircle2}
        title="Sin clientes prioritarios hoy"
        description="No hay clientes en riesgo o con oportunidad activa en tu cartera para hoy."
      />
    );
  }

  const valorMaximo = Math.max(...clientes.map((c) => c.score_desglose.valor_historico));

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {clientes.map((cliente) => (
        <PriorityCard
          key={cliente.cliente_id} cliente={cliente} valorMaximo={valorMaximo}
          onClick={() => onSelect(cliente.cliente_id)}
        />
      ))}
    </div>
  );
};
