import { api } from './http';
import type { AnomaliaResponse } from '../types/admin';

export const detectAnomaly = (transaccion_id: string) =>
  api.get<AnomaliaResponse>('/api/v1/analytics/admin/anomalies', {
    params: { transaccion_id },
  });

export const getMLOpsStatus = () =>
  api.get('/api/v1/admin/mlops/status');
