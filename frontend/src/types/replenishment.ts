// Espejo de backend/app/schemas/replenishment.py (Reabastecimiento Inteligente,
// docs/features/plan_reabastecimiento_inteligente.md). Cada campo derivado declara su
// procedencia al lado (`metodo_demanda`, `lead_time_origen`, `metodo_stock_seguridad`).

export type MetodoDemanda = 'ml_demand_rf' | 'estadistico' | 'sin_historia';
export type LeadTimeOrigen = 'producto' | 'categoria' | 'proveedor' | 'default';
export type MetodoStockSeguridad = 'estocastico' | 'determinista' | 'sin_historia';
export type RiesgoReabastecimiento = 'critico' | 'alto' | 'medio' | 'bajo' | 'sin_demanda';
export type ClaseABC = 'A' | 'B' | 'C';
export type ClaseXYZ = 'X' | 'Y' | 'Z';

export interface ItemReabastecimiento {
  codart: string;
  nombre: string;
  clase_abc: string;
  clase_xyz: string;
  stock_actual: number;
  costo_unitario: number;
  demanda_diaria_media: number;
  demanda_diaria_sigma: number;
  metodo_demanda: MetodoDemanda;
  coeficiente_variacion: number | null;
  lead_time_dias: number;
  lead_time_origen: LeadTimeOrigen;
  nivel_servicio: number;
  z_usado: number | null;
  stock_seguridad: number;
  metodo_stock_seguridad: MetodoStockSeguridad;
  punto_reorden: number;
  cobertura_dias: number | null;
  riesgo: RiesgoReabastecimiento;
  cantidad_sugerida: number;
  costo_total_sugerido: number;
  prioridad_score: number;
  razones: string[];
}

export interface ResumenReabastecimiento {
  total_articulos_evaluados: number;
  productos_riesgo_critico: number;
  productos_riesgo_alto: number;
  productos_con_recomendacion_compra: number;
  costo_total_compra_sugerida: number;
  cobertura_mediana_dias: number | null;
  cobertura_promedio_dias: number | null;
}

// ── Configuración editable (§6.3) ────────────────────────────────────────────────
export interface PoliticaABC {
  clase_abc: string;
  nivel_servicio: number;
}

export interface LeadTimeConfig {
  id: number;
  producto: string | null;
  categoria: string | null;
  proveedor: string | null;
  dias: number;
}

// ── F7: Alertas inteligentes ─────────────────────────────────────────────────────
export interface AlertaReabastecimiento {
  tipo: 'cambio_brusco_demanda' | 'tendencia_decreciente';
  severidad: 'media' | 'baja';
  codart: string;
  nombre: string;
  mensaje: string;
  accion_url: string;
}

// ── F8: Simulador what-if (solo lectura, no persiste) ────────────────────────────
export interface SimularReabastecimientoRequest {
  almacen?: string | null;
  categoria?: string | null;
  proveedor?: string | null;
  tipo_movimiento?: string | null;
  horizonte_dias?: number | null;
  niveles_servicio?: Record<string, number> | null;
  lead_time_default_dias?: number | null;
}

export interface SimularReabastecimientoResponse {
  resumen_actual: ResumenReabastecimiento;
  resumen_simulado: ResumenReabastecimiento;
  parametros_simulados: Record<string, unknown>;
}

// ── F9: propuestas de compra persistidas (bloque 5, Gestión Operativa) ───────────
export type EstadoPropuestaCompra = 'borrador' | 'aprobada' | 'rechazada' | 'exportada';

export interface CrearPropuestaRequest {
  almacen?: string | null;
  categoria?: string | null;
  proveedor?: string | null;
  tipo_movimiento?: string | null;
  horizonte_dias?: number | null;
  solo_criticos?: boolean;
  riesgo?: string | null;
  clase_abc?: string | null;
  clase_xyz?: string | null;
}

export interface PropuestaCompraLinea {
  codart: string;
  nombre: string;
  cantidad: number;
  costo_unitario: number;
  costo_total: number;
  justificacion: Record<string, unknown>;
}

export interface PropuestaCompra {
  id: number;
  estado: EstadoPropuestaCompra;
  usuario_id: number | null;
  filtros_origen: Record<string, unknown>;
  horizonte_dias: number;
  total: number;
  creado_en: string;
  actualizado_en: string;
}

export interface PropuestaCompraDetalle extends PropuestaCompra {
  lineas: PropuestaCompraLinea[];
}
