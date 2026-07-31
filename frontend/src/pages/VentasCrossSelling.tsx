import { Badge } from '../components/ui/Badge';
import { SaleAssistant } from '../components/crossSelling/SaleAssistant';
import { ClientProfileCard } from '../components/crossSelling/ClientProfileCard';
import { IntelligentCombosPanel } from '../components/crossSelling/IntelligentCombosPanel';
import { useCrossSellStore } from '../store/crossSellStore';

/** Módulo de Venta Cruzada (docs/auditoria/25_modulo_cross_selling.md): página propia
 * bajo /ventas/cross-selling, mismo patrón que Metas y Comisiones (VendorGoalDashboard) --
 * no una sección embebida en el dashboard general de Ventas.
 *
 * Orden jerárquico (revisión de usabilidad 2026-07-28, a pedido del usuario): el
 * selector de cliente vive DENTRO de `SaleAssistant` (cliente y asistente son una sola
 * herramienta de trabajo, no dos paneles separados) -- es lo primero que usa el
 * vendedor. El Perfil 360 va INMEDIATAMENTE después del Asistente (no al final de la
 * página) porque es el resultado directo de elegir cliente ahí mismo -- separarlo con
 * Combos Inteligentes en medio dejaba el estado vacío "Busca un cliente para empezar"
 * desconectado de dónde se busca al cliente. Combos Inteligentes cierra la página
 * (otra vía de venta cruzada, pero de uso secundario frente al asistente). Se retiró
 * el panel "Top combinaciones" (cards "Combo # más vendido junto"): quedó redundante
 * con la estrategia "Oferta Estrella" de Combos Inteligentes, que muestra la misma
 * coocurrencia real de facturas con más contexto. */
export const VentasCrossSelling = () => {
  const cliente = useCrossSellStore((s) => s.cliente);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap justify-between items-center gap-3 animate-fade-in">
        <div>
          <h1 className="text-3xl font-display font-semibold text-slate-100">Venta Cruzada</h1>
          <p className="text-sm text-slate-500 mt-0.5">Asistente de recomendaciones y combinaciones de productos más vendidas</p>
        </div>
        <Badge variant="info" dot>ML Activo — Filtrado Colaborativo Item-Item</Badge>
      </div>

      <SaleAssistant clienteId={cliente?.cliente_id ?? null} />

      {cliente && <ClientProfileCard cliente={cliente} />}

      <div>
        <h3 className="font-sans font-semibold text-slate-200 mb-4">Combos inteligentes</h3>
        <IntelligentCombosPanel clienteId={cliente?.cliente_id ?? null} />
      </div>
    </div>
  );
};
