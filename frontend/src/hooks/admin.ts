import { useQuery } from '@tanstack/react-query';
import {
  getAdminResumen, getAuditLogs, getMLOpsStatus, getModelsStatus, getSystemHealth,
} from '../services/admin';
import type { AuditLogFilters } from '../types/admin';
import type { PaginationQuery } from '../types/pagination';
import { getApiErrorMessage as errorMessage } from '../utils/apiError';

// Estado del pipeline de reentrenamiento (running/idle/logs) -- no consumido aún por
// ningún dashboard; se deja como parity hook del endpoint /admin/modelos/status.
export const useMLOpsStatus = () => {
  const query = useQuery({
    queryKey: ['admin', 'mlops-status'],
    queryFn: () => getMLOpsStatus().then((r) => r.data),
  });
  return { data: query.data ?? null, loading: query.isLoading, error: errorMessage(query.error), refetch: query.refetch };
};

export const useModelsStatus = () => {
  const query = useQuery({
    queryKey: ['admin', 'models-status'],
    queryFn: () => getModelsStatus().then((r) => r.data),
  });
  return { data: query.data ?? [], loading: query.isLoading, error: errorMessage(query.error) };
};

export const useAdminResumen = () => {
  const query = useQuery({
    queryKey: ['admin', 'resumen'],
    queryFn: () => getAdminResumen().then((r) => r.data),
  });
  return { data: query.data ?? null, loading: query.isLoading, error: errorMessage(query.error) };
};

export const useSystemHealth = () => {
  const query = useQuery({
    queryKey: ['admin', 'system-health'],
    queryFn: () => getSystemHealth().then((r) => r.data),
  });
  return { data: query.data ?? null, loading: query.isLoading, error: errorMessage(query.error) };
};

export const useAuditLogs = (pagination: PaginationQuery, filters: AuditLogFilters = {}) => {
  const query = useQuery({
    queryKey: ['admin', 'audit-logs', pagination, filters],
    queryFn: () => getAuditLogs(pagination, filters).then((r) => r.data),
  });
  return {
    data: query.data?.items ?? [],
    total: query.data?.total ?? 0,
    totalPages: query.data?.total_pages ?? 0,
    loading: query.isLoading,
    error: errorMessage(query.error),
  };
};
