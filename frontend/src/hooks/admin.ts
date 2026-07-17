import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  actualizarAnomaliaRevision, detectAnomaly, getAnomaliaRevisiones, getAuditLogs, getMLOpsStatus, getModelsStatus,
  getSystemHealth,
} from '../services/admin';
import type { AnomaliaEstado, AuditLogFilters } from '../types/admin';
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

// Fase 2 Admin (docs/features/plan_correcciones_pendientes.md §3): cola de triage de
// anomalías -- separa "nueva" de lo ya trabajado, en vez de un resultado puntual que
// se pierde al cerrar la pantalla.
export const useAnomaliaRevisiones = (pagination: PaginationQuery, estado?: AnomaliaEstado) => {
  const query = useQuery({
    queryKey: ['admin', 'anomalia-revisiones', pagination, estado],
    queryFn: () => getAnomaliaRevisiones(pagination, estado).then((r) => r.data),
  });
  return {
    data: query.data?.items ?? [],
    total: query.data?.total ?? 0,
    totalPages: query.data?.total_pages ?? 0,
    loading: query.isLoading,
    error: errorMessage(query.error),
    refetch: query.refetch,
  };
};

export const useActualizarAnomaliaRevision = () => {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: ({ id, estado, nota }: { id: number; estado: AnomaliaEstado; nota?: string }) =>
      actualizarAnomaliaRevision(id, estado, nota).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'anomalia-revisiones'] });
    },
  });
  return {
    execute: mutation.mutate,
    loading: mutation.isPending,
    error: errorMessage(mutation.error),
  };
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
