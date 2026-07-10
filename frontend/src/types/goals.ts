export interface GoalProposal {
  id: number;
  vendedor: string;
  sucursal: string;
  monto_meta: number;
  comision_base_pct: number;
  estado: string;
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
