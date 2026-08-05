import { api } from './http';
import type {
  AdminResumen, AuditLogEntry, AuditLogFilters, ModelStatus, SystemHealth,
} from '../types/admin';
import type { Page, PaginationQuery } from '../types/pagination';

export const getMLOpsStatus = () =>
  api.get('/api/v1/admin/modelos/status');

export const getModelsStatus = () =>
  api.get<ModelStatus[]>('/api/v1/admin/modelos/models');

export const getSystemHealth = () =>
  api.get<SystemHealth>('/api/v1/analytics/admin/system-health');

export const getAdminResumen = () =>
  api.get<AdminResumen>('/api/v1/analytics/admin/resumen');

export const getAuditLogs = (pagination: PaginationQuery, filters: AuditLogFilters = {}) =>
  api.get<Page<AuditLogEntry>>('/api/v1/analytics/admin/audit-logs', {
    params: { ...pagination, ...filters },
  });
