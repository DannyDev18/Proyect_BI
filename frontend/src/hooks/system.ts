import { useQuery } from '@tanstack/react-query';
import { getProvenance } from '../services/system';

const errorMessage = (error: unknown): string | null =>
  error ? (error instanceof Error ? error.message : 'Error al cargar datos') : null;

// Refresca cada 5 min: procedencia de datos, no requiere tiempo real (docs/auditoria/
// 33_actualizacion_modulo_gerencia.md, H4).
export const useProvenance = () => {
  const query = useQuery({
    queryKey: ['system', 'provenance'],
    queryFn: () => getProvenance().then((r) => r.data),
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  });
  return { data: query.data ?? null, loading: query.isLoading, error: errorMessage(query.error) };
};
