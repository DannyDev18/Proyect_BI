import { useState } from 'react';
import { X } from 'lucide-react';
import { ChartCard } from '../ui/ChartCard';
import { Autocomplete } from '../ui/Autocomplete';
import { Badge } from '../ui/Badge';
import { SuggestionCard } from './SuggestionCard';
import { SimulacionPanel } from './SimulacionPanel';
import { useCrossSellSugerencias, useSearchClientes, useSearchProductos } from '../../hooks/crossSelling';
import { useCrossSellStore } from '../../store/crossSellStore';
import type { ClienteBusqueda, ProductoBusqueda, SugerenciaProducto } from '../../types/crossSelling';

interface SaleAssistantProps {
  clienteId: string | null;
}

/** Asistente de Venta Cruzada: el vendedor elige el cliente y arma una canasta
 * simulada (búsqueda de producto por código/nombre) y ve sugerencias en vivo. No es
 * un carrito transaccional -- el ERP SAP sigue siendo el único sistema que factura
 * (docs/auditoria/25_modulo_cross_selling.md §0). `cliente`/`canasta` viven en Zustand
 * (`crossSellStore`) porque otros paneles hermanos no anidados (perfil 360, combos)
 * también los necesitan. El selector de cliente vive en esta misma tarjeta (revisión
 * de usabilidad 2026-07-28): cliente y asistente son una sola herramienta de trabajo
 * para el vendedor, no dos pasos separados. */
export const SaleAssistant = ({ clienteId }: SaleAssistantProps) => {
  const cliente = useCrossSellStore((s) => s.cliente);
  const setCliente = useCrossSellStore((s) => s.setCliente);
  const canasta = useCrossSellStore((s) => s.canasta);
  const agregarACanastaStore = useCrossSellStore((s) => s.agregarACanasta);
  const quitarDeCanasta = useCrossSellStore((s) => s.quitarDeCanasta);
  const [busqueda, setBusqueda] = useState('');
  const [busquedaCliente, setBusquedaCliente] = useState('');

  const search = useSearchProductos(busqueda);
  const clientesEncontrados = useSearchClientes(busquedaCliente);
  const sugerencias = useCrossSellSugerencias(canasta.map((c) => c.codart), clienteId);

  const agregarACanasta = (codart: string, nombre: string) => {
    agregarACanastaStore({ codart, nombre });
    setBusqueda('');
  };

  const agregarSugerencia = (s: SugerenciaProducto) => {
    agregarACanasta(s.codart, s.nombre);
  };

  const ultimoProductoOrigen = canasta.at(-1)?.codart ?? '';

  return (
    <ChartCard
      title="Asistente de Venta Cruzada"
      badge={{ label: 'Reglas de Asociación', variant: 'ml' }}
      height="h-auto"
    >
      <div className="space-y-4">
        <div>
          <p className="text-[11px] uppercase tracking-widest text-slate-500 mb-2">Cliente</p>
          {cliente ? (
            <Badge variant="info" className="pr-1">
              {cliente.nombre} <span className="font-mono text-xs opacity-70 ml-1">{cliente.cliente_id}</span>
              <button onClick={() => setCliente(null)} className="ml-1 hover:text-danger">
                <X size={12} />
              </button>
            </Badge>
          ) : (
            <Autocomplete<ClienteBusqueda>
              placeholder="Busca por cédula/RUC o nombre del cliente…"
              label="Cliente activo del asistente"
              loading={clientesEncontrados.loading}
              options={clientesEncontrados.data}
              onQueryChange={setBusquedaCliente}
              getKey={(c) => c.cliente_id}
              onSelect={setCliente}
              renderOption={(c) => (
                <span className="flex justify-between">
                  <span className="truncate">{c.nombre}</span>
                  <span className="text-slate-500 font-mono text-xs ml-2 shrink-0">{c.cliente_id}</span>
                </span>
              )}
            />
          )}
          {cliente && (
            <p className="text-xs text-slate-500 mt-2">
              Sugerencias personalizadas y excluyendo productos ya comprados por{' '}
              <span className="text-slate-300">{cliente.nombre}</span>.
            </p>
          )}
        </div>

        <div className="pt-4 border-t border-slate-800">
          <p className="text-[11px] uppercase tracking-widest text-slate-500 mb-2">Productos de la canasta</p>
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

          {canasta.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-3">
              {canasta.map((item) => (
                <Badge key={item.codart} variant="info" className="pr-1">
                  {item.nombre}
                  <button onClick={() => quitarDeCanasta(item.codart)} className="ml-1 hover:text-danger">
                    <X size={12} />
                  </button>
                </Badge>
              ))}
            </div>
          )}

          {canasta.length > 0 && <SimulacionPanel items={canasta.map((c) => c.codart)} clienteId={clienteId} />}
        </div>

        <div className="pt-4 border-t border-slate-800">
          <p className="text-[11px] uppercase tracking-widest text-slate-500 mb-2">Sugerencias de venta cruzada</p>
          {canasta.length === 0 ? (
            <p className="text-sm text-slate-500 py-6 text-center">
              Agrega al menos un producto a la canasta para ver sugerencias de venta cruzada.
            </p>
          ) : sugerencias.loading ? (
            <div className="space-y-2">
              {[0, 1, 2].map((i) => <div key={i} className="skeleton h-16 rounded-lg" />)}
            </div>
          ) : sugerencias.data?.sugerencias.length ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {sugerencias.data.sugerencias.map((s, i) => (
                <SuggestionCard
                  key={s.codart}
                  sugerencia={s}
                  productoOrigenCod={ultimoProductoOrigen}
                  clienteId={clienteId}
                  onAgregar={agregarSugerencia}
                  esPrincipal={i === 0}
                />
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-500 py-6 text-center">
              No hay sugerencias disponibles para esta canasta.
            </p>
          )}
        </div>
      </div>
    </ChartCard>
  );
};
