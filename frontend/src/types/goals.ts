export interface GoalProposal {
  id: number;
  vendedor: string;
  vendedor_origen: string;
  monto_meta: number;
  comision_base_pct: number;
  estado: string;
}

// Desglose del motor estadístico IQR para un vendedor -- transparencia del cálculo
// (plan_actualizacion_modulo_metas_comisiones.md Fase 2 ítem 1). Espejo de
// backend/app/schemas/analytics.py::MetaSugeridaResponse.
export interface MetaSugeridaDesglose {
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

export interface GoalPeriod {
  anio: number;
  mes: number;
}

export interface GoalPeriodOption extends GoalPeriod {
  label: string;
}

// ── Integración ML: Metas y Comisiones (docs/auditoria/15_...) ──────────────────────
export interface VendorRiskItem {
  nombre: string;
  ventas: number;
  meta: number;
  pct_cumplimiento: number;
  pct_esperado_a_la_fecha: number;
  estado: string;
}

export interface CategoryRecommendationItem {
  categoria_origen: string;
  categoria_sugerida: string;
  producto_sugerido: string;
  score_afinidad: number;
}

export interface GoalsAISummary {
  vendedores_en_riesgo: VendorRiskItem[];
  vendedores_alta_probabilidad: VendorRiskItem[];
  recomendaciones_por_categoria: CategoryRecommendationItem[];
}

// ── Comisiones (docs/modulo_metas.md, docs/auditoria/17_...) ────────────────────────
export type NivelComision = 'EXCELENTE' | 'META' | 'CERCA' | 'LEJOS';

export interface VendorCommissionRow {
  id: number;
  vendedor: string;
  monto_meta: number;
  venta_real: number;
  pct_cumplimiento: number;
  nivel: NivelComision;
  tasa_aplicada_pct: number;
  comision_devengada: number;
  estado: string;
  // Comisiones Variables (docs/features/plan_integracion_comisiones_variables.md):
  // null salvo que el backend corra en modo "sombra"/"variable" (COMISION_MODO).
  comision_variable?: number | null;
  nivel_variable?: NivelComision | null;
}
