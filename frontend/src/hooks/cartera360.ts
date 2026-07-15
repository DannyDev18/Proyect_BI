import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getListaTrabajo, getDetalleCliente, registrarGestion, getTasaRecuperacion } from '../services/cartera360';
import type { RegistrarGestionRequest } from '../types/cartera360';
import { qk } from '../constants/queryKeys';

const errorMessage = (error: unknown): string | null =>
  error ? (error instanceof Error ? error.message : 'Error al cargar datos') : null;

const wrap = <T,>(query: { data?: T; isLoading: boolean; error: unknown; refetch: () => unknown }) => ({
  data: query.data ?? null,
  loading: query.isLoading,
  error: errorMessage(query.error),
  refetch: query.refetch,
});

export const useListaTrabajo = () =>
  wrap(useQuery({
    queryKey: qk.cartera360.listaTrabajo(),
    queryFn: () => getListaTrabajo().then((r) => r.data),
  }));

export const useDetalleCliente = (clienteId: string | null) =>
  wrap(useQuery({
    queryKey: qk.cartera360.detalleCliente(clienteId ?? ''),
    queryFn: () => getDetalleCliente(clienteId as string).then((r) => r.data),
    enabled: !!clienteId,
  }));

export const useTasaRecuperacion = () =>
  wrap(useQuery({
    queryKey: qk.cartera360.tasaRecuperacion(),
    queryFn: () => getTasaRecuperacion().then((r) => r.data),
  }));

export const useRegistrarGestion = () => {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (body: RegistrarGestionRequest) => registrarGestion(body).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.cartera360.tasaRecuperacion() });
    },
  });
  return {
    execute: mutation.mutate,
    loading: mutation.isPending,
    error: errorMessage(mutation.error),
  };
};
