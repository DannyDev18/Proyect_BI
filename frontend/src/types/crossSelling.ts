// Tipos del módulo Venta Cruzada — contratos de backend/app/schemas/cross_selling.py
// (docs/features/plan_modulo_cross_selling.md, auditoría 25).

export interface SugerenciaProducto {
  codart: string;
  nombre: string;
  precio: number;
  categoria: string;
  score: number;
  motivo: string;
  fuente: string;
}

export interface CrossSellSugerenciasResponse {
  items: string[];
  sugerencias: SugerenciaProducto[];
}

export type EventoRecomendacion = 'mostrada' | 'aceptada' | 'rechazada';

export interface CrossSellEventoRequest {
  producto_origen_cod: string;
  producto_sugerido_cod: string;
  evento: EventoRecomendacion;
  score_lift?: number | null;
  motivo?: string | null;
  cliente_id?: string | null;
}

export interface CrossSellKpis {
  sugerencias_mostradas: number;
  sugerencias_aceptadas: number;
  sugerencias_rechazadas: number;
  tasa_conversion_pct: number;
}

export interface ProductoBusqueda {
  codart: string;
  nombre: string;
  categoria: string;
  precio: number;
}
