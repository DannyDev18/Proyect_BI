import { api } from './http';
import type { VentasKPIs, ChurnResponse, RecomendacionResponse, SegmentacionResponse } from '../types/ventas';

export const getSalesGoals = () =>
  api.get<VentasKPIs>('/api/v1/analytics/ventas/goals');

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
