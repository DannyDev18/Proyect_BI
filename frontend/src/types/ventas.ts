import type { ClienteRuta, EfectividadComercial, ProximaAccion } from './cartera360';

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
 * ::get_sales_performance). `cumplimiento_actual` es venta real acumulada del período en
 * dólares (no un porcentaje pese al nombre) -- el % se deriva en el frontend dividiendo
 * por `meta_mensual` (auditoría A-0.4, docs/features/plan_correcciones_integrales_
 * sistema.md §2.4: un tipo `VentasKPIs` con campos inventados -- `ventas_actuales`,
 * `cumplimiento_pct`, `clientes_activos` -- que nunca existieron en el backend real
 * estaba siendo consumido por `DashboardVentas.tsx`, rompiendo 3 de 4 KPI cards del
 * dashboard principal de Ventas; corregido para usar este tipo, el único que coincide
 * con el contrato real). */
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

// (`ForecastCierre` -- "Pronóstico de cierre" del vendedor, modelo `sales_rf` -- se
// retiró por completo, auditoría 49.)
export interface MetaSugerida {
  vendedor_origen: string;
  meta_sugerida_estadistica: number;
  metodo_estadistico: string;
  meses_historico_usados: number;
  valores_atipicos_excluidos: number;
  meses_atipicos_ml_detectados: number;
  componente_estacional: number | null;
  componente_tendencia: number;
  factor_tendencia_aplicado: number;
  coeficiente_variacion: number;
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
  // Tramo real de cumplimiento configurable (auditoría 45), no el enum fijo legacy --
  // p.ej. "Sin comisión", "Meta", "Sobrecumplimiento alto".
  nivel: string;
  tasa_aplicada_pct: number;
  bono_aplicado: number;
  comision_devengada: number;
  dias_restantes_mes: number;
  en_alerta_cierre: boolean;
  mensaje_alerta: string | null;
  // Comisión única y variable (docs/features/plan_motor_metas_v3_y_comisiones_
  // unificadas.md, Fase 1, R-1) -- sin esquema plano paralelo ni modo condicionante.
  desglose_variable?: DesgloseComisionVariable | null;
}

export interface DesgloseLineaComision {
  codart: string;
  grupo: string;
  base_comisionable: number;
  tasa_pct: number;
  factor_estrategico: number;
  factor_credito: number;
  comision_linea: number;
  sin_costo: boolean;
  pendiente_aprobacion: boolean;
}

export interface DesgloseComisionVariable {
  comision_base: number;
  comision_post_tipo: number;
  nivel: NivelComision;
  multiplicador_cumplimiento: number;
  comision_post_cumplimiento: number;
  devoluciones_estimadas: number;
  bonos_total: number;
  comision_final: number;
  desglose_lineas: DesgloseLineaComision[];
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

// ── Dashboard "Mi Negocio" del vendedor (auditoría 43, Fase 5) ──────────────────────

export interface CuotaVendedor {
  meta_mensual: number;
  venta_actual: number;
  pct_cumplimiento: number;
  nivel: NivelComision;
}

export interface ComisionResumenVendedor {
  comision_devengada: number;
  tasa_aplicada_pct: number;
  bono_aplicado: number;
  dias_restantes_mes: number;
}

export interface MetaDiariaVendedor {
  objetivo_diario: number | null;
  venta_hoy: number;
}

export interface RankingVendedor {
  posicion: number;
  total: number;
}

export interface EvolucionMensualPunto {
  anio: number;
  mes: number;
  venta_real: number;
  meta: number;
}

export interface ComparativoMesAnterior {
  venta_mes_actual: number;
  venta_mes_anterior: number;
  variacion_pct: number;
}

export interface ProductoVendedor {
  codart: string;
  nombre: string;
  venta: number;
  unidades: number;
}

export interface MiNegocio {
  vendedor_origen: string;
  anio: number;
  mes: number;
  cuota: CuotaVendedor;
  comision: ComisionResumenVendedor;
  meta_diaria: MetaDiariaVendedor;
  ranking: RankingVendedor | null;
  evolucion_mensual: EvolucionMensualPunto[];
  comparativo_mes_anterior: ComparativoMesAnterior | null;
  top_productos: ProductoVendedor[];
  clientes_en_riesgo: ClienteRuta[];
  pipeline: ClienteRuta[];
  proximas_acciones: ProximaAccion[];
  efectividad_comercial: EfectividadComercial;
}
