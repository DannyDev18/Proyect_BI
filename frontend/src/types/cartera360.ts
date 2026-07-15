// Tipos del módulo Ventas — Cartera de Clientes 360
// (docs/features/propuesta_nuevos_modulos_roi.md §4, auditoría 32)
// Contratos de backend/app/schemas/cartera360.py

export interface ClienteListaTrabajo {
  cliente_id: string;
  nombre_cliente: string;
  num_compras: number;
  dias_sin_comprar: number;
  valor_historico: number;
  frecuencia_promedio_dias: number | null;
  alerta_caida_frecuencia: boolean;
  /** Churn real del modelo (churn_rf), 0-100. Ya viene calculado en la lista de trabajo. */
  probabilidad_abandono: number;
  prioridad: number;
}

export interface ListaTrabajo {
  clientes: ClienteListaTrabajo[];
}

export interface ProductoRecomendadoCliente {
  producto_cod: string;
  score: number;
}

export interface DetalleCliente {
  cliente_id: string;
  probabilidad_abandono: number;
  riesgo_alto: boolean;
  segmento: number;
  nombre_segmento: string;
  productos_recomendados: ProductoRecomendadoCliente[];
}

export type EventoGestion = 'contactado' | 'recompro' | 'perdido';

export interface RegistrarGestionRequest {
  cliente_id: string;
  evento: EventoGestion;
  motivo?: string | null;
}

export interface RegistrarGestionResponse {
  id: number;
  evento: string;
}

export interface TasaRecuperacion {
  total_gestiones: number;
  recompras: number;
  tasa_recuperacion_pct: number;
}
