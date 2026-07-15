import { useQuery, useMutation } from '@tanstack/react-query';
import { detectAnomaly, getAuditLogs, getMLOpsStatus, getModelsStatus } from '../services/admin';
import type { AuditLogFilters } from '../types/admin';
import type { PaginationQuery } from '../types/pagination';

const errorMessage = (error: unknown): string | null =>
  error ? (error instanceof Error ? error.message : 'Error al cargar datos') : null;

export const useAnomalyDetector = () => {
  const mutation = useMutation({
    mutationFn: (transaccion_id: string) => detectAnomaly(transaccion_id).then((r) => r.data),
  });
  return {
    data: mutation.data ?? null,
    loading: mutation.isPending,
    error: errorMessage(mutation.error),
    execute: (transaccion_id: string) => { mutation.reset(); mutation.mutate(transaccion_id); },
  };
};

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
