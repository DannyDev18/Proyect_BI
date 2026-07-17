export interface GerenciaKPIs {
  // Calculado en backend (docs/auditoria/33_actualizacion_modulo_gerencia.md, H2) --
  // antes el frontend lo reconstruía sumando `ventas_por_sucursal`, una fuente que
  // excluye sucursales con neto exactamente 0 y podía divergir del total real.
  ingresos_totales: number;
  ventas_consolidadas?: number;
  ticket_promedio: number;
  margen_utilidad_neta: number;
  roi_estimado: number;
  ventas_por_sucursal: Record<string, number>;
  ventas_por_vendedor?: Record<string, number>;
  // Fase 2 Gerencia (docs/features/plan_correcciones_pendientes.md §3): comparativa vs.
  // período anterior de igual longitud -- null sin start_date/end_date explícitos.
  ingresos_totales_tendencia_pct: number | null;
  margen_utilidad_neta_tendencia_pct: number | null;
  ticket_promedio_tendencia_pct: number | null;
  roi_estimado_tendencia_pct: number | null;
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
