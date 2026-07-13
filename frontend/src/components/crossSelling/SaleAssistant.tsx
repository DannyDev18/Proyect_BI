import { useState } from 'react';
import { X } from 'lucide-react';
import { ChartCard } from '../ui/ChartCard';
import { Autocomplete } from '../ui/Autocomplete';
import { AlertBadge } from '../ui/AlertBadge';
import { SuggestionCard } from './SuggestionCard';
import { useCrossSellSugerencias, useSearchProductos } from '../../hooks/crossSelling';
import type { ProductoBusqueda, SugerenciaProducto } from '../../types/crossSelling';

interface CanastaItem {
  codart: string;
  nombre: string;
}

interface SaleAssistantProps {
  clienteId: string | null;
}

/** Asistente de Venta Cruzada: el vendedor arma una canasta simulada (búsqueda de
 * producto por código/nombre) y ve sugerencias en vivo. No es un carrito
 * transaccional -- el ERP SAP sigue siendo el único sistema que factura
 * (docs/auditoria/25_modulo_cross_selling.md §0). */
export const SaleAssistant = ({ clienteId }: SaleAssistantProps) => {
  const [canasta, setCanasta] = useState<CanastaItem[]>([]);
  const [busqueda, setBusqueda] = useState('');

  const search = useSearchProductos(busqueda);
  const sugerencias = useCrossSellSugerencias(canasta.map((c) => c.codart), clienteId);

  const agregarACanasta = (codart: string, nombre: string) => {
    if (canasta.some((c) => c.codart === codart)) return;
    setCanasta((prev) => [...prev, { codart, nombre }]);
    setBusqueda('');
  };

  const agregarSugerencia = (s: SugerenciaProducto) => {
    agregarACanasta(s.codart, s.nombre);
  };

  const quitarDeCanasta = (codart: string) => {
    setCanasta((prev) => prev.filter((c) => c.codart !== codart));
  };

  const ultimoProductoOrigen = canasta.at(-1)?.codart ?? '';

  return (
    <ChartCard
      title="Asistente de Venta Cruzada"
      badge={{ label: 'Reglas de Asociación', variant: 'ml' }}
      height="h-auto"
    >
      <div className="space-y-4">
        <Autocomplete<ProductoBusqueda>
          placeholder="Escribe el código o nombre del producto…"
          label="Agregar producto a la canasta simulada"
          loading={search.loading}
          options={search.data}
          onQueryChange={setBusqueda}
          getKey={(p) => p.codart}
          onSelect={(p) => agregarACanasta(p.codart, p.nombre)}
          renderOption={(p) => (
            <span className="flex justify-between">
              <span className="truncate">{p.nombre}</span>
              <span className="text-slate-500 font-mono text-xs ml-2 shrink-0">{p.codart}</span>
            </span>
          )}
        />

        {/* Canasta simulada */}
        {canasta.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {canasta.map((item) => (
              <AlertBadge key={item.codart} variant="info" className="pr-1">
                {item.nombre}
                <button onClick={() => quitarDeCanasta(item.codart)} className="ml-1 hover:text-red-400">
                  <X size={12} />
                </button>
              </AlertBadge>
            ))}
          </div>
        )}

        {/* Sugerencias */}
        {canasta.length === 0 ? (
          <p className="text-sm text-slate-500 py-6 text-center">
            Agrega al menos un producto a la canasta para ver sugerencias de venta cruzada.
          </p>
        ) : sugerencias.loading ? (
          <div className="space-y-2">
            {[0, 1, 2].map((i) => <div key={i} className="skeleton h-16 rounded-lg" />)}
          </div>
        ) : sugerencias.data?.sugerencias.length ? (
          <div className="space-y-2">
            {sugerencias.data.sugerencias.map((s) => (
              <SuggestionCard
                key={s.codart}
                sugerencia={s}
                productoOrigenCod={ultimoProductoOrigen}
                clienteId={clienteId}
                onAgregar={agregarSugerencia}
              />
            ))}
          </div>
        ) : (
          <p className="text-sm text-slate-500 py-6 text-center">
            No hay sugerencias disponibles para esta canasta.
          </p>
        )}
      </div>
    </ChartCard>
  );
};
