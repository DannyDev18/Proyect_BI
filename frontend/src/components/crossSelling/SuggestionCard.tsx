import { useEffect, useRef } from 'react';
import { Plus } from 'lucide-react';
import type { SugerenciaProducto } from '../../types/crossSelling';
import { useCrossSellEvento } from '../../hooks/crossSelling';

interface SuggestionCardProps {
  sugerencia: SugerenciaProducto;
  productoOrigenCod: string;
  clienteId: string | null;
  onAgregar: (sugerencia: SugerenciaProducto) => void;
  esPrincipal?: boolean;
}

/** Tarjeta de una sugerencia de venta cruzada. Dispara el evento 'mostrada' al
 * renderizarse (una sola vez por sugerencia) y 'aceptada' al hacer clic en Agregar
 * (docs/auditoria/25_modulo_cross_selling.md, RN-CS2). La primera sugerencia
 * (`esPrincipal`) se destaca con un layout más ancho (jerarquía visual). */
export const SuggestionCard = ({
  sugerencia, productoOrigenCod, clienteId, onAgregar, esPrincipal = false,
}: SuggestionCardProps) => {
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
    <div
      className={`rounded-lg border transition-colors ${
        esPrincipal
          ? 'border-primary/30 bg-primary/5 hover:border-primary/50 p-4 md:col-span-2'
          : 'border-slate-800 hover:border-slate-700 py-3 px-3'
      }`}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className={`font-medium text-slate-200 truncate ${esPrincipal ? 'text-base' : 'text-sm'}`}>{sugerencia.nombre}</p>
          <p className="text-xs text-slate-500 font-mono">
            {sugerencia.codart} · ${sugerencia.precio.toFixed(2)}
            {sugerencia.margen_unitario != null && (
              <span className="text-success"> · +${sugerencia.margen_unitario.toFixed(2)} margen</span>
            )}
          </p>
          <p className="text-xs text-slate-500 mt-1 italic truncate">{sugerencia.motivo}</p>
        </div>
        <button
          onClick={handleAgregar}
          className="shrink-0 flex items-center gap-1 px-3 py-1.5 bg-primary hover:bg-accent text-white text-xs font-semibold rounded-lg transition-colors"
        >
          <Plus size={13} /> Agregar
        </button>
      </div>
    </div>
  );
};
