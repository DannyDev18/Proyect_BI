import { api } from './http';
import type { AnomaliaResponse, AuditLogEntry, AuditLogFilters, ModelStatus } from '../types/admin';
import type { Page, PaginationQuery } from '../types/pagination';

export const detectAnomaly = (transaccion_id: string) =>
  api.get<AnomaliaResponse>('/api/v1/analytics/admin/anomalies', {
    params: { transaccion_id },
  });

export const getMLOpsStatus = () =>
  api.get('/api/v1/admin/modelos/status');

export const getModelsStatus = () =>
  api.get<ModelStatus[]>('/api/v1/admin/modelos/models');

export const getAuditLogs = (pagination: PaginationQuery, filters: AuditLogFilters = {}) =>
  api.get<Page<AuditLogEntry>>('/api/v1/analytics/admin/audit-logs', {
    params: { ...pagination, ...filters },
  });
