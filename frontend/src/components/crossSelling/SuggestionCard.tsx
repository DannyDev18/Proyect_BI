import { useEffect, useRef } from 'react';
import { Plus } from 'lucide-react';
import type { SugerenciaProducto } from '../../types/crossSelling';
import { useCrossSellEvento } from '../../hooks/crossSelling';

interface SuggestionCardProps {
  sugerencia: SugerenciaProducto;
  productoOrigenCod: string;
  clienteId: string | null;
  onAgregar: (sugerencia: SugerenciaProducto) => void;
}

/** Tarjeta de una sugerencia de venta cruzada. Dispara el evento 'mostrada' al
 * renderizarse (una sola vez por sugerencia) y 'aceptada' al hacer clic en Agregar
 * (docs/auditoria/25_modulo_cross_selling.md, RN-CS2). */
export const SuggestionCard = ({ sugerencia, productoOrigenCod, clienteId, onAgregar }: SuggestionCardProps) => {
  const evento = useCrossSellEvento();
  const yaNotificoMostrada = useRef(false);

  useEffect(() => {
    if (yaNotificoMostrada.current) return;
    yaNotificoMostrada.current = true;
    evento.mutate({
      producto_origen_cod: productoOrigenCod,
      producto_sugerido_cod: sugerencia.codart,
      evento: 'mostrada',
      score_lift: sugerencia.score,
      motivo: sugerencia.motivo,
      cliente_id: clienteId,
      // eslint-disable-next-line react-hooks/exhaustive-deps
    });
  }, [sugerencia.codart]);

  const handleAgregar = () => {
    evento.mutate({
      producto_origen_cod: productoOrigenCod,
      producto_sugerido_cod: sugerencia.codart,
      evento: 'aceptada',
      score_lift: sugerencia.score,
      motivo: sugerencia.motivo,
      cliente_id: clienteId,
    });
    onAgregar(sugerencia);
  };

  return (
    <div className="flex items-center justify-between gap-3 py-3 px-3 rounded-lg border border-slate-800 hover:border-slate-700 transition-colors">
      <div className="min-w-0">
        <p className="text-sm font-medium text-slate-200 truncate">{sugerencia.nombre}</p>
        <p className="text-xs text-slate-500 font-mono">{sugerencia.codart} · ${sugerencia.precio.toFixed(2)}</p>
        <p className="text-xs text-slate-500 mt-1 italic truncate">{sugerencia.motivo}</p>
      </div>
      <button
        onClick={handleAgregar}
        className="shrink-0 flex items-center gap-1 px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold rounded-lg transition-colors"
      >
        <Plus size={13} /> Agregar
      </button>
    </div>
  );
};
