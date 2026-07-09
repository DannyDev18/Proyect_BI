import { useQuery, useMutation } from '@tanstack/react-query';
import { getSalesGoals, getChurnRisk, getRecommendations, getCustomerSegment } from '../services/ventas';
import { qk } from '../constants/queryKeys';

const errorMessage = (error: unknown): string | null =>
  error ? (error instanceof Error ? error.message : 'Error al cargar datos') : null;

export const useSalesGoals = () => {
  const query = useQuery({
    queryKey: qk.ventas.goals(),
    queryFn: () => getSalesGoals().then((r) => r.data),
  });
  return { data: query.data ?? null, loading: query.isLoading, error: errorMessage(query.error), refetch: query.refetch };
};

export const useChurnRisk = () => {
  const mutation = useMutation({
    mutationFn: (cliente_id: string) => getChurnRisk(cliente_id).then((r) => r.data),
  });
  return {
    data: mutation.data ?? null,
    loading: mutation.isPending,
    error: errorMessage(mutation.error),
    execute: (cliente_id: string) => { mutation.reset(); mutation.mutate(cliente_id); },
  };
};

export const useRecommendations = () => {
  const mutation = useMutation({
    mutationFn: (cliente_id: string) => getRecommendations(cliente_id).then((r) => r.data),
  });
  return {
    data: mutation.data ?? null,
    loading: mutation.isPending,
    error: errorMessage(mutation.error),
    execute: (cliente_id: string) => { mutation.reset(); mutation.mutate(cliente_id); },
  };
};

export const useCustomerSegment = () => {
  const mutation = useMutation({
    mutationFn: (cliente_cod: string) => getCustomerSegment(cliente_cod).then((r) => r.data),
  });
  return {
    data: mutation.data ?? null,
    loading: mutation.isPending,
    error: errorMessage(mutation.error),
    execute: (cliente_cod: string) => { mutation.reset(); mutation.mutate(cliente_cod); },
  };
};
