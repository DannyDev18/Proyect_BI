import { AlertTriangle, MapPin, ShoppingBag, TrendingUp } from 'lucide-react';
import { Badge } from '../ui/Badge';
import { ErrorState } from '../ui/ErrorState';
import { EmptyState } from '../ui/EmptyState';
import { usePerfilCliente } from '../../hooks/crossSelling';
import { fmtMoney, timeAgo } from '../../utils/format';
import type { ClienteBusqueda } from '../../types/crossSelling';
import { WhyExplanationPanel } from './WhyExplanationPanel';

const Metric = ({ label, value }: { label: string; value: string }) => (
  <div>
    <p className="text-[11px] uppercase tracking-widest text-slate-500">{label}</p>
    <p className="font-mono text-sm text-slate-200 mt-0.5">{value}</p>
  </div>
);

const MetricSkeleton = () => (
  <div>
    <div className="skeleton h-2.5 w-16 rounded mb-2" />
    <div className="skeleton h-4 w-20 rounded" />
  </div>
);

/** Fase 1 de docs/features/plan_refactor_venta_cruzada_ia.md (CAMBIO 1): perfil 360
 * del cliente seleccionado, con skeleton por sección y estado vacío real cuando el
 * cliente no tiene historial suficiente -- nunca ceros que se lean como "sin valor".
 * No renderiza nada sin cliente (el padre, `VentasCrossSelling`, ya no monta este
 * componente hasta que hay uno elegido) -- feedback de usuario 2026-07-28: mostrar aquí
 * un segundo bloque "Busca un cliente para empezar" duplicaba el buscador que ya vive
 * dentro de `SaleAssistant`, dando la impresión de dos puntos de búsqueda distintos. */
export const ClientProfileCard = ({ cliente }: { cliente: ClienteBusqueda }) => {
  const perfil = usePerfilCliente(cliente.cliente_id);

  if (perfil.loading) {
    return (
      <div className="card p-6 space-y-4">
        <div className="skeleton h-5 w-48 rounded" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <MetricSkeleton /><MetricSkeleton /><MetricSkeleton /><MetricSkeleton />
        </div>
      </div>
    );
  }

  if (perfil.error) {
    return (
      <div className="card p-6">
        <ErrorState message={perfil.error} onRetry={perfil.refetch} />
      </div>
    );
  }

  const p = perfil.data;
  if (!p) return null;

  return (
    <div className="card p-6 animate-fade-in-up">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
        <div>
          <h3 className="font-sans font-semibold text-slate-100">{p.nombre}</h3>
          <p className="text-xs text-slate-500 font-mono mt-0.5 flex items-center gap-1">
            {p.cliente_id}
            {p.ciudad && (
              <span className="flex items-center gap-0.5 ml-2 text-slate-500">
                <MapPin size={11} /> {p.ciudad}
              </span>
            )}
          </p>
        </div>
        <div className="flex gap-2 flex-wrap justify-end">
          {p.nombre_segmento && <Badge variant="primary">{p.nombre_segmento}</Badge>}
          {p.riesgo_alto_abandono && (
            <Badge variant="danger">
              <AlertTriangle size={11} /> Riesgo de fuga
            </Badge>
          )}
        </div>
      </div>

      {!p.tiene_historial ? (
        <EmptyState
          icon={ShoppingBag}
          title="Sin historial de compras"
          description="Este cliente no tiene ventas registradas todavía en el EDW. Las sugerencias se apoyarán solo en las características del producto."
        />
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Metric label="Valor histórico" value={fmtMoney(p.valor_historico)} />
          <Metric label="Ticket promedio" value={fmtMoney(p.ticket_promedio)} />
          <Metric label="Compras (12m)" value={String(p.frecuencia_12m ?? 0)} />
          <Metric label="Última compra" value={p.ultima_compra ? timeAgo(p.ultima_compra) : '—'} />
          {p.probabilidad_recompra != null && (
            <Metric label="Prob. de recompra" value={`${p.probabilidad_recompra.toFixed(0)}%`} />
          )}
          {p.categoria_favorita && <Metric label="Categoría favorita" value={p.categoria_favorita} />}
          {p.antiguedad_dias != null && (
            <Metric label="Cliente desde hace" value={`${Math.floor(p.antiguedad_dias / 30)} meses`} />
          )}
        </div>
      )}

      {p.productos_favoritos.length > 0 && (
        <div className="mt-4 pt-4 border-t border-slate-800">
          <p className="text-[11px] uppercase tracking-widest text-slate-500 mb-2 flex items-center gap-1">
            <TrendingUp size={11} /> Productos favoritos
          </p>
          <div className="flex flex-wrap gap-2">
            {p.productos_favoritos.map((prod) => (
              <Badge key={prod.codart} variant="neutral">{prod.nombre}</Badge>
            ))}
          </div>
        </div>
      )}

      {p.tiene_historial && <WhyExplanationPanel clienteId={p.cliente_id} />}
    </div>
  );
};
