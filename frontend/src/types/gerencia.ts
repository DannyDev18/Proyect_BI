export interface GerenciaKPIs {
  // Calculado en backend (docs/auditoria/33_actualizacion_modulo_gerencia.md, H2) --
  // antes el frontend lo reconstruía sumando `ventas_por_sucursal`, una fuente que
  // excluye sucursales con neto exactamente 0 y podía divergir del total real.
  ingresos_totales: number;
  ticket_promedio: number;
  margen_utilidad_neta: number;
  // docs/auditoria/39_madurez_bi_toma_decisiones.md, H-02: reemplaza a `roi_estimado`
  // (`margen * 1.15`). RN-BI2: retorno sobre costo de mercadería vendida. `null` cuando no
  // hay costo con el que comparar -- mostrar "sin base de cálculo", nunca 0%.
  roi_real: number | null;
  costo_mercaderia: number;
  ventas_por_sucursal: Record<string, number>;
  ventas_por_vendedor?: Record<string, number>;
  // Fase 2 Gerencia (docs/features/plan_correcciones_pendientes.md §3): comparativa vs.
  // período anterior de igual longitud -- null sin start_date/end_date explícitos.
  ingresos_totales_tendencia_pct: number | null;
  margen_utilidad_neta_tendencia_pct: number | null;
  ticket_promedio_tendencia_pct: number | null;
  roi_real_tendencia_pct: number | null;
  // G-04 (docs/features/plan_madurez_bi_toma_decisiones.md): contra qué período se comparan
  // las tendencias, y por qué alguna no tiene base. `null` sin fechas explícitas.
  comparacion: ContextoComparacion | null;
}

/** Modos de comparación temporal soportados por `GET /analytics/gerencia/kpis`. */
export type ModoComparacion = 'periodo_anterior' | 'anio_anterior' | 'promedio_n_periodos';

export const MODO_COMPARACION_LABEL: Record<ModoComparacion, string> = {
  periodo_anterior: 'Período anterior',
  anio_anterior: 'Mismo período del año anterior',
  promedio_n_periodos: 'Promedio de 3 períodos previos',
};

export interface ContextoComparacion {
  modo: ModoComparacion;
  desde_referencia: string;
  hasta_referencia: string;
  periodos_promediados: number;
  /** Motivos por los que una tendencia vino en null. Se muestran; no se pinta 0%. */
  sin_base: string[] | null;
}

// Campos nullables: cuando la serie filtrada (vendedor/almacén/sucursal) no tiene datos,
// el backend degrada con gracia y devuelve metricas vacías en vez de un 500 (ver
// backend/app/schemas/analytics.py::MetricasPrediccion).
export interface MetricasPrediccion {
  ventas_acumuladas: number | null;
  venta_esperada: number | null;
  crecimiento_esperado: number | null;
  mes_mayor_venta: string | null;
  mes_menor_venta: string | null;
  promedio_mensual: number | null;
  mae_modelo: number | null;
  r2_modelo: number | null;
  nivel_confianza: number | null;
  fecha_entrenamiento: string | null;
  algoritmo: string | null;
}

export interface SalesPredictionPoint {
  fecha: string;
  monto_real?: number;
  monto_predicho?: number;
  intervalo_inferior?: number;
  intervalo_superior?: number;
}

export type SalesPredictionGranularidad = 'semana' | 'mes';

export interface SalesPredictionResponse {
  granularidad: SalesPredictionGranularidad;
  periodos_proyectados: number;
  historial_y_prediccion: SalesPredictionPoint[];
  metricas: MetricasPrediccion;
  insights: string[];
}

// Fase 2 Gerencia (docs/features/plan_correcciones_pendientes.md §3): KPI de
// cumplimiento vs metas del dashboard principal -- agregado company-wide de metas
// APROBADA del período (public.metas_comerciales_operativas), sin ML.
export interface CumplimientoMetaPeriodo {
  anio: number;
  mes: number;
  monto_meta_total: number;
  venta_real_total: number;
  pct_cumplimiento: number;
  vendedores_con_meta_aprobada: number;
}
