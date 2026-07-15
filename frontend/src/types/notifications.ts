// Espejo de backend/app/schemas/notification.py
// (docs/features/plan_modulo_notificaciones.md, docs/auditoria/31_modulo_notificaciones.md).

export type PrioridadNotificacion = 'alta' | 'media' | 'baja';

export interface Notificacion {
  id: number | null;
  tipo_evento: string;
  titulo: string;
  mensaje: string;
  accion_url: string | null;
  prioridad: PrioridadNotificacion;
  fecha_creacion: string | null;
  leida: boolean;
  persistida: boolean;
}
