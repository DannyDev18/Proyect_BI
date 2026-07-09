import { useQuery, useMutation } from '@tanstack/react-query';
import { detectAnomaly, getMLOpsStatus } from '../services/admin';

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

// Not consumed by any page yet — parity hook for the getMLOpsStatus service (see DashboardAdmin.tsx's MODEL_STATUS mock).
export const useMLOpsStatus = () => {
  const query = useQuery({
    queryKey: ['admin', 'mlops-status'],
    queryFn: () => getMLOpsStatus().then((r) => r.data),
  });
  return { data: query.data ?? null, loading: query.isLoading, error: errorMessage(query.error), refetch: query.refetch };
};
