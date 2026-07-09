export interface GerenciaKPIs {
  ventas_consolidadas?: number;
  ticket_promedio: number;
  margen_utilidad_neta: number;
  roi_estimado: number;
  ventas_por_sucursal: Record<string, number>;
  ventas_por_vendedor?: Record<string, number>;
}

export interface MetricasPrediccion {
  ventas_acumuladas: number;
  venta_esperada: number;
  crecimiento_esperado: number;
  mes_mayor_venta: string;
  mes_menor_venta: string;
  promedio_mensual: number;
  mae_modelo: number;
  nivel_confianza: number;
  fecha_entrenamiento: string;
}

export interface SalesPredictionPoint {
  fecha: string;
  monto_real?: number;
  monto_predicho?: number;
  intervalo_inferior?: number;
  intervalo_superior?: number;
}

export interface SalesPredictionResponse {
  horizonte: string;
  dias_proyectados: number;
  historial_y_prediccion: SalesPredictionPoint[];
  metricas: MetricasPrediccion;
  insights: string[];
}
