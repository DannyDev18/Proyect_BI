import { useState } from 'react';
import { X } from 'lucide-react';
import { AlertBadge } from '../components/ui/AlertBadge';
import { Autocomplete } from '../components/ui/Autocomplete';
import { TopCombinacionesPanel } from '../components/crossSelling/TopCombinacionesPanel';
import { SaleAssistant } from '../components/crossSelling/SaleAssistant';
import { useSearchClientes } from '../hooks/crossSelling';
import type { ClienteBusqueda } from '../types/crossSelling';

/** Módulo de Venta Cruzada (docs/auditoria/25_modulo_cross_selling.md): página propia
 * bajo /ventas/cross-selling, mismo patrón que Metas y Comisiones (VendorGoalDashboard) --
 * no una sección embebida en el dashboard general de Ventas. */
export const VentasCrossSelling = () => {
  const [cliente, setCliente] = useState<ClienteBusqueda | null>(null);
  const [busquedaCliente, setBusquedaCliente] = useState('');
  const clientesEncontrados = useSearchClientes(busquedaCliente);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap justify-between items-center gap-3 animate-fade-in">
        <div>
          <h1 className="text-3xl font-display font-semibold text-slate-100">Venta Cruzada</h1>
          <p className="text-sm text-slate-500 mt-0.5">Asistente de recomendaciones y combinaciones de productos más vendidas</p>
        </div>
        <AlertBadge variant="info" dot>ML Activo — Filtrado Colaborativo Item-Item</AlertBadge>
      </div>

      <TopCombinacionesPanel />

      {/* Cliente opcional: personaliza las sugerencias excluyendo lo ya comprado */}
      <div className="card p-6 animate-fade-in-up stagger-1">
        <h3 className="font-sans font-semibold text-slate-200 mb-4">Cliente (opcional)</h3>
        {cliente ? (
          <AlertBadge variant="info" className="pr-1">
            {cliente.nombre} <span className="font-mono text-xs opacity-70 ml-1">{cliente.cliente_id}</span>
            <button onClick={() => setCliente(null)} className="ml-1 hover:text-danger">
              <X size={12} />
            </button>
          </AlertBadge>
        ) : (
          <Autocomplete<ClienteBusqueda>
            placeholder="Busca por cédula/RUC o nombre del cliente…"
            label="Personalizar sugerencias por cliente"
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
            Excluyendo productos ya comprados por <span className="text-slate-300">{cliente.nombre}</span>.
          </p>
        )}
      </div>

      <SaleAssistant clienteId={cliente?.cliente_id ?? null} />
    </div>
  );
};
