import { Badge } from '../components/ui/Badge';
import { SmartKpiRow } from '../components/rutaInteligente/SmartKpiRow';
import { RouteList } from '../components/rutaInteligente/RouteList';
import { ClientDetailDrawer, type DrawerClienteInfo } from '../components/rutaInteligente/ClientDetailDrawer';
import { AlertsSummary } from '../components/rutaInteligente/AlertsSummary';
import { UpcomingActions } from '../components/rutaInteligente/UpcomingActions';
import { useRutaHoy, useProximasAcciones } from '../hooks/cartera360';
import { useRutaVentasStore } from '../store/rutaVentasStore';

/** "Mi Ruta Inteligente de Ventas" (docs/features/plan_refactor_cartera360_ruta_
 * inteligente.md): página propia bajo /ventas/ruta, conviviendo con /ventas/cartera360
 * (estrategia de migración §7 -- estrangulamiento, no big-bang). Orquestador delgado:
 * toda la lógica de priorización/agregación vive en el backend (`Cartera360Service.
 * get_ruta_hoy`), esta página solo compone los paneles ya construidos.
 *
 * Feedback de usuario 2026-07-28: "Efectividad Comercial" y "Plan semanal sugerido" se
 * retiraron de esta página -- la primera necesita volumen de gestiones que hoy no existe
 * (D-1) y se ve vacía casi siempre; el segundo era solo un reparto mecánico de la misma
 * lista que ya se ve arriba. Se reemplazaron por `AlertsSummary` (triage por
 * clasificación) y `UpcomingActions` (agenda de próximas acciones) -- ambos derivados de
 * los datos que `/ruta/hoy` YA trae, sin llamadas nuevas al backend. Los endpoints/
 * componentes de Efectividad y Plan semanal se conservan en el backend/`hooks` (no se
 * borraron, siguen probados) por si se retoman más adelante desde otra vista, p. ej. un
 * reporte de gerencia con suficiente volumen de datos. */
export const VentasRuta = () => {
  const { data, loading, error, refetch } = useRutaHoy();
  const proximasAcciones = useProximasAcciones();
  const clienteAbiertoId = useRutaVentasStore((s) => s.clienteAbiertoId);
  const abrirCliente = useRutaVentasStore((s) => s.abrirCliente);

  // Auditoría 43 (H43-13): el drawer puede abrirse desde la ruta priorizada del día
  // (ClienteRuta completo) o desde "Próximas acciones" (ProximaAccion, un conjunto de
  // clientes deliberadamente distinto) -- se busca en ambas fuentes.
  const clienteDeRuta = data?.clientes.find((c) => c.cliente_id === clienteAbiertoId);
  const clienteDeProxima = proximasAcciones.data?.acciones.find((a) => a.cliente_id === clienteAbiertoId);
  const clienteAbierto: DrawerClienteInfo | null =
    clienteDeRuta ??
    (clienteDeProxima
      ? {
          cliente_id: clienteDeProxima.cliente_id,
          nombre_cliente: clienteDeProxima.nombre_cliente,
          ultima_gestion_evento: clienteDeProxima.ultimo_evento,
          ultima_gestion_fecha: clienteDeProxima.ultima_gestion_fecha,
        }
      : null);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap justify-between items-center gap-3 animate-fade-in">
        <div>
          <h1 className="text-3xl font-display font-semibold text-slate-100">Mi Ruta Inteligente de Ventas</h1>
          <p className="text-sm text-slate-500 mt-0.5">Ruta priorizada del día, con motivo explicable y oferta sugerida</p>
        </div>
        <Badge variant="info" dot>ML Activo — churn_rf · segmentation · association</Badge>
      </div>

      <SmartKpiRow tarjetas={data?.tarjetas ?? null} loading={loading} />

      <div>
        <h3 className="font-sans font-semibold text-slate-200 mb-4">Prioridades de hoy</h3>
        <RouteList
          clientes={data?.clientes ?? []} loading={loading} error={error}
          onRetry={refetch} onSelect={abrirCliente}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card p-6">
          <h3 className="font-sans font-semibold text-slate-200 mb-4">Resumen de alertas</h3>
          <AlertsSummary clientes={data?.clientes ?? []} />
        </div>
        <div className="card p-6">
          <h3 className="font-sans font-semibold text-slate-200 mb-4">Próximas acciones</h3>
          <UpcomingActions onSelect={abrirCliente} />
        </div>
      </div>

      <ClientDetailDrawer cliente={clienteAbierto} />
    </div>
  );
};
