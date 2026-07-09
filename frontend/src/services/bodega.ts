import { api } from './http';
import type { BodegaKPIs, DemandaResponse } from '../types/bodega';

export const getBodegaKPIs = () =>
  api.get<BodegaKPIs>('/api/v1/analytics/bodega/kpis-inventory');

export const getDemandForecast = (producto_cod: string) =>
  api.get<DemandaResponse>('/api/v1/analytics/bodega/demand-forecasting', {
    params: { producto_cod },
  });
