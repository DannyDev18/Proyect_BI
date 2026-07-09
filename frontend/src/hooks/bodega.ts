import { useQuery, useMutation } from '@tanstack/react-query';
import { getBodegaKPIs, getDemandForecast } from '../services/bodega';
import { qk } from '../constants/queryKeys';

const errorMessage = (error: unknown): string | null =>
  error ? (error instanceof Error ? error.message : 'Error al cargar datos') : null;

export const useBodegaKPIs = () => {
  const query = useQuery({
    queryKey: qk.bodega.kpis(),
    queryFn: () => getBodegaKPIs().then((r) => r.data),
  });
  return { data: query.data ?? null, loading: query.isLoading, error: errorMessage(query.error), refetch: query.refetch };
};

export const useDemandForecast = () => {
  const mutation = useMutation({
    mutationFn: (producto_cod: string) => getDemandForecast(producto_cod).then((r) => r.data),
  });
  return {
    data: mutation.data ?? null,
    loading: mutation.isPending,
    error: errorMessage(mutation.error),
    // reset() first so a new search clears the previous result immediately (parity with the old useAsyncParam behavior)
    execute: (producto_cod: string) => { mutation.reset(); mutation.mutate(producto_cod); },
  };
};
