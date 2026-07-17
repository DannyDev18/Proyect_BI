export interface AnomaliaResponse {
  transaccion_id: string;
  score: number;
  es_anomalia: boolean;
}

export type AnomaliaEstado = 'nueva' | 'revisada' | 'descartada' | 'confirmada';

export interface AnomaliaRevision {
  id: number;
  transaccion_id: string;
  score: number;
  estado: AnomaliaEstado;
  revisor_id: number | null;
  nota: string | null;
  fecha_deteccion: string;
  fecha_revision: string | null;
}

export interface RoleData {
  id: number;
  nombre: string;
}

export interface UserData {
  id: number;
  nombre: string;
  email: string;
  es_activo: boolean;
  sucursal: string | null;
  id_vendedor_origen: string | null;
  codalm: string | null;
  role: { id: number; nombre: string };
  rol_id?: number;
}

export interface UserPayload {
  nombre: string;
  email: string;
  rol_id: number;
  sucursal: string | null;
  id_vendedor_origen: string | null;
  codalm: string | null;
  todos_los_almacenes?: boolean;
  password?: string;
}

export interface AlmacenOption {
  codalm: string;
  nombre_almacen: string;
}

export interface ModelStatus {
  name: string;
  r2: number | null;
  status: string;
}

export type AuditLevel = 'INFO' | 'WARN' | 'ERROR';

export interface AuditLogEntry {
  ts: string;
  level: AuditLevel;
  source: string;
  msg: string;
}

export interface AuditLogFilters {
  fecha_desde?: string;
  fecha_hasta?: string;
  usuario?: string;
  modulo?: string;
}

export interface EtlControlEntry {
  tabla_destino: string;
  estado: string | null;
  ultimo_etl_ok: string | null;
  registros_cargados: number | null;
  duracion_seg: number | null;
  mensaje_error: string | null;
  fecha_ejecucion: string | null;
}

export interface SystemHealth {
  etl_detalle: EtlControlEntry[];
  logins_fallidos_ventana_horas: number;
  logins_fallidos_conteo: number;
}
