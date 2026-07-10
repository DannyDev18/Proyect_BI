import { api } from './http';
import type {
  VentasKPIs, VentasGoalsTracking, ChurnResponse, RecomendacionResponse, SegmentacionResponse,
  ForecastCierre, MetaSugerida, RecomendacionesComerciales,
} from '../types/ventas';

export const getSalesGoals = () =>
  api.get<VentasKPIs>('/api/v1/analytics/ventas/goals');

/** Mismo endpoint que `getSalesGoals`, tipado según el contrato real del backend
 * (`VentasGoalsTracking`) -- usado por el dashboard vendedor. */
export const getMyGoalTracking = () =>
  api.get<VentasGoalsTracking>('/api/v1/analytics/ventas/goals');

/** Integración ML (docs/auditoria/15_...): pronóstico de cierre (modelo `sales_rf`),
 * meta sugerida (IA `goals_rf` + motor estadístico) y recomendaciones comerciales
 * (reglas de asociación) para el vendedor autenticado. */
export const getGoalForecastCierre = () =>
  api.get<ForecastCierre>('/api/v1/analytics/ventas/goals/forecast-cierre');

export const getMetaSugerida = () =>
  api.get<MetaSugerida>('/api/v1/analytics/ventas/goals/meta-sugerida');

export const getGoalRecommendations = () =>
  api.get<RecomendacionesComerciales>('/api/v1/analytics/ventas/goals/recomendaciones');

export const getChurnRisk = (cliente_id: string) =>
  api.get<ChurnResponse>('/api/v1/analytics/ventas/churn-risk', {
    params: { cliente_id },
  });

export const getRecommendations = (cliente_id: string) =>
  api.get<RecomendacionResponse>('/api/v1/analytics/ventas/recommendations', {
    params: { cliente_id },
  });

export const getCustomerSegment = (cliente_cod: string) =>
  api.get<SegmentacionResponse>(`/api/v1/analytics/ventas/clientes/${cliente_cod}/segmento`);
