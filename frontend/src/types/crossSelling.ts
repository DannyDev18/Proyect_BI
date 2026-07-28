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
  margen_unitario: number | null;
  factor_margen: number;
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
  margen_unitario: number | null;
}

export interface ClienteBusqueda {
  cliente_id: string;
  nombre: string;
  // Campos opcionales (Fase 1, plan_refactor_venta_cruzada_ia.md CAMBIO 1): `null`
  // cuando el cliente no tiene historial de compras, no 0/vacío inventado.
  ciudad?: string | null;
  ultima_compra?: string | null;
  frecuencia_12m?: number | null;
  n_compras?: number | null;
}

export interface ProductoFavorito {
  codart: string;
  nombre: string;
}

export interface SimulacionVenta {
  ticket_estimado: number;
  productos_no_encontrados: string[];
  margen_estimado: number | null;
  incremento_vs_ticket_promedio_cliente: number | null;
  probabilidad_recompra: number | null;
  explicacion: string;
}

export interface ProductoCombo {
  codart: string;
  nombre: string;
  precio: number;
  categoria: string;
  margen_unitario: number | null;
}

export interface CombinacionInteligente {
  nombre: string;
  estrategia: string;
  productos: ProductoCombo[];
  margen_esperado: number | null;
  afinidad: number | null;
  popularidad: number | null;
  porque: string;
}

export interface FeatureContribucion {
  feature: string;
  valor: number;
  contribucion: number;
}

export interface ChurnExplicacion {
  cliente_id: string;
  contribuciones: FeatureContribucion[];
}

export interface PerfilCliente {
  cliente_id: string;
  nombre: string;
  ciudad: string | null;
  tiene_historial: boolean;
  num_compras: number | null;
  ultima_compra: string | null;
  antiguedad_dias: number | null;
  valor_historico: number | null;
  ticket_promedio: number | null;
  frecuencia_12m: number | null;
  categoria_favorita: string | null;
  productos_favoritos: ProductoFavorito[];
  segmento: number | null;
  nombre_segmento: string | null;
  probabilidad_recompra: number | null;
  riesgo_alto_abandono: boolean | null;
}

