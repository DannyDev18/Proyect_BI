import { api } from './http';
import type {
  AnomaliaEstado, AnomaliaResponse, AnomaliaRevision, AuditLogEntry, AuditLogFilters, ModelStatus, SystemHealth,
} from '../types/admin';
import type { Page, PaginationQuery } from '../types/pagination';

export const detectAnomaly = (transaccion_id: string) =>
  api.get<AnomaliaResponse>('/api/v1/analytics/admin/anomalies', {
    params: { transaccion_id },
  });

export const getAnomaliaRevisiones = (pagination: PaginationQuery, estado?: AnomaliaEstado) =>
  api.get<Page<AnomaliaRevision>>('/api/v1/analytics/admin/anomalies/revisiones', {
    params: { ...pagination, estado },
  });

export const actualizarAnomaliaRevision = (id: number, estado: AnomaliaEstado, nota?: string) =>
  api.patch<AnomaliaRevision>(`/api/v1/analytics/admin/anomalies/revisiones/${id}`, { estado, nota });

export const getMLOpsStatus = () =>
  api.get('/api/v1/admin/modelos/status');

export const getModelsStatus = () =>
  api.get<ModelStatus[]>('/api/v1/admin/modelos/models');

export const getSystemHealth = () =>
  api.get<SystemHealth>('/api/v1/analytics/admin/system-health');

export const getAuditLogs = (pagination: PaginationQuery, filters: AuditLogFilters = {}) =>
  api.get<Page<AuditLogEntry>>('/api/v1/analytics/admin/audit-logs', {
    params: { ...pagination, ...filters },
  });
