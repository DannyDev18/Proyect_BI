export interface VentasKPIs {
  meta_mensual: number;
  ventas_actuales: number;
  cumplimiento_pct: number;
  clientes_activos: number;
  churn_promedio?: number;
}

export interface ChurnResponse {
  cliente_id: string;
  probabilidad_abandono: number;
  riesgo_alto: boolean;
}

export interface RecommendedProduct {
  producto_cod: string;
  nombre?: string;
  confianza?: number;
  lift?: number;
}

export interface RecomendacionResponse {
  cliente_id: string;
  recomendaciones: RecommendedProduct[];
}

export interface SegmentacionResponse {
  cliente_id: string;
  segmento: number;
  nombre_segmento: string;
}

/** Forma real de la respuesta de GET /analytics/ventas/goals (VPKPIVentas en el backend,
 * ver backend/app/schemas/analytics.py y backend/app/repositories/analytics_repository.py
 * ::get_sales_performance). No confundir con `VentasKPIs` (arriba), que no coincide con
 * el contrato real del backend. */
export interface RankingVendedorItem {
  nombre: string;
  ventas: number;
  meta: number;
  cumple: boolean;
}

export interface VentasGoalsTracking {
  meta_mensual: number;
  cumplimiento_actual: number;
  meta_proyectada: number;
  ranking_vendedores: RankingVendedorItem[];
}

/** Integración ML: Metas y Comisiones (docs/auditoria/15_...). */
export interface ForecastCierre {
  sucursal: string;
  dias_restantes: number;
  ventas_mes_actual: number;
  proyeccion_cierre: number;
  meta: number;
  pct_cumplimiento_esperado: number;
  probabilidad_alcanzar_meta: number | null;
  mae_modelo: number | null;
}

export interface MetaSugerida {
  vendedor_origen: string;
  meta_sugerida_estadistica: number;
  metodo_estadistico: string;
  meses_historico_usados: number;
  valores_atipicos_excluidos: number;
  meses_atipicos_ml_detectados: number;
}

export interface RecomendacionComercialItem {
  producto_cod: string;
  score_afinidad: number;
}

export interface RecomendacionesComerciales {
  vendedor_origen: string;
  recomendaciones: RecomendacionComercialItem[];
}

// ── Comisiones (docs/modulo_metas.md, docs/auditoria/17_...) ────────────────────────
export type NivelComision = 'EXCELENTE' | 'META' | 'CERCA' | 'LEJOS';

export interface MiComision {
  vendedor_origen: string;
  anio: number;
  mes: number;
  monto_meta: number;
  venta_real: number;
  pct_cumplimiento: number;
  nivel: NivelComision;
  tasa_aplicada_pct: number;
  bono_aplicado: number;
  comision_devengada: number;
  dias_restantes_mes: number;
  en_alerta_cierre: boolean;
  mensaje_alerta: string | null;
}

export interface PostGoalInvoiceItem {
  num_factura: string;
  fecha: string;
  monto_factura: number;
  acumulado_venta: number;
}

export interface PostGoalInvoicesResponse {
  facturas: PostGoalInvoiceItem[];
}
