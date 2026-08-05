export interface GoalProposal {
  id: number;
  vendedor: string;
  vendedor_origen: string;
  monto_meta: number;
  comision_base_pct: number;
  estado: string;
  // Estado real del vendedor en el EDW (edw.dim_vendedor.activo) -- petición explícita
  // del usuario: verificar si el vendedor sigue activo antes de aprobar su meta.
  activo: boolean;
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
  // Motor v2 (docs/auditoria/46_motor_metas_configurable.md, plan_motor_metas_configurable.md):
  anio_objetivo: number;
  mes_objetivo: number;
  indice_estacional_aplicado: number;
  fuente_indice_estacional: 'propio' | 'empresa' | 'neutro';
  referencia_alcanzable: number;
  banda_actuo: boolean;
  meta_pre_banda: number;
  meta_unidades_estadistica: number;
  es_trazabilidad_persistida: boolean;
}

/** Configuración modular del motor de metas v3 (docs/features/plan_motor_metas_v3_y_
 * comisiones_unificadas.md §9/§18, Fase 6): una fila por etapa del pipeline -- reemplaza
 * por completo al motor v2 plano de 13 constantes como fuente real del motor (ese
 * endpoint se conserva en el backend por compatibilidad, sin cliente frontend). */
export interface MetaConfigModulo {
  etapa: string;
  metodo: string | null;
  activo: boolean;
  orden: number;
  parametros: Record<string, unknown>;
  razon_desactivacion: string | null;
  actualizado_en: string;
}

export interface MetaConfigModuloMetodo {
  implementado: boolean;
  descripcion: string;
  motivo: string | null;
}

/** Un parámetro numérico editable de la etapa -- fuente única para que el frontend
 * genere un campo de formulario (no un editor de JSON crudo). */
export interface MetaConfigModuloParametro {
  clave: string;
  label: string;
  tipo: 'int' | 'float';
  min: number;
  max: number;
  paso: number;
  default: number;
}

export interface MetaConfigModuloCatalogoEtapa {
  orden: number;
  nombre: string;
  metodos: Record<string, MetaConfigModuloMetodo>;
  parametros: MetaConfigModuloParametro[];
}

export type MetaConfigCatalogo = Record<string, MetaConfigModuloCatalogoEtapa>;

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

export interface ComponenteFormulaTraza {
  orden: number;
  componente: string;
  operador: 'sumar' | 'restar' | 'multiplicar';
  monto: number;
  acumulado_tras_paso: number;
}

export interface VendorCommissionRow {
  id: number;
  vendedor: string;
  monto_meta: number;
  venta_real: number;
  pct_cumplimiento: number;
  // Tramo real de cumplimiento configurable (auditoría 45), no el enum fijo legacy.
  nivel: string;
  tasa_aplicada_pct: number;
  comision_devengada: number;
  estado: string;
  // Comisión única y variable (docs/features/plan_motor_metas_v3_y_comisiones_
  // unificadas.md, Fase 1, R-1/R-3) -- sin esquema plano paralelo. `componentes` es
  // el desglose de los 7 pasos de la fórmula, expandible en la tabla.
  componentes: ComponenteFormulaTraza[];
}
