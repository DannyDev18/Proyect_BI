import { useState } from 'react';
import { Drawer } from '../ui/Drawer';
import { Tabs } from '../ui/Tabs';
import { QuickLogForm } from './QuickLogForm';
import { ClientTimeline } from './ClientTimeline';
import { useRutaVentasStore } from '../../store/rutaVentasStore';

/** Subconjunto estructural de `ClienteRuta` (Auditoría 43): el drawer se abre tanto
 * desde la ruta priorizada del día (`ClienteRuta` completo) como desde el panel de
 * "Próximas acciones" (`ProximaAccion`, un conjunto de clientes deliberadamente
 * DISTINTO -- ver H43-13), que no trae `motivo` ni el resto de la priorización. Solo lo
 * que el drawer realmente renderiza se declara como requerido. */
export interface DrawerClienteInfo {
  cliente_id: string;
  nombre_cliente: string;
  motivo?: string;
  ultima_gestion_evento?: string | null;
  ultima_gestion_fecha?: string | null;
}

interface ClientDetailDrawerProps {
  cliente: DrawerClienteInfo | null;
  /** Auditoría 43 (Fase 5): `DashboardVentas.tsx` mantiene su propio estado local del
   * cliente abierto (no el de `rutaVentasStore`, que es específico de "Mi Ruta
   * Inteligente"). Por defecto usa el store, para no romper `VentasRuta.tsx`. */
  onClose?: () => void;
}

/** Panel lateral de un cliente de la ruta: reutiliza `Drawer` (ya cubre lo que el plan
 * llamaba "Sheet lateral" en DEC-1 -- no hace falta un primitivo nuevo). Gestionar +
 * Historial en pestañas para no scrollear una página larga por cliente. */
export const ClientDetailDrawer = ({ cliente, onClose }: ClientDetailDrawerProps) => {
  const cerrarClienteRuta = useRutaVentasStore((s) => s.cerrarCliente);
  const [tab, setTab] = useState<'gestionar' | 'historial'>('gestionar');

  return (
    <Drawer open={!!cliente} onClose={onClose ?? cerrarClienteRuta} title={cliente?.nombre_cliente ?? ''}>
      {cliente && (
        <div className="space-y-5">
          <div className="text-xs text-slate-500 space-y-1">
            <p><span className="text-slate-600">Motivo:</span> {cliente.motivo}</p>
            {cliente.ultima_gestion_evento && (
              <p><span className="text-slate-600">Última gestión:</span> {cliente.ultima_gestion_evento} ({cliente.ultima_gestion_fecha})</p>
            )}
          </div>

          <Tabs
            items={[{ value: 'gestionar', label: 'Gestionar' }, { value: 'historial', label: 'Historial' }]}
            value={tab} onChange={(v) => setTab(v as 'gestionar' | 'historial')}
          />

          {tab === 'gestionar' ? (
            <QuickLogForm clienteId={cliente.cliente_id} onSuccess={() => setTab('historial')} />
          ) : (
            <ClientTimeline clienteId={cliente.cliente_id} />
          )}
        </div>
      )}
    </Drawer>
  );
};
