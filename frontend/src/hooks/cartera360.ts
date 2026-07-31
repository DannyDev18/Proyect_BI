import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  getListaTrabajo, getDetalleCliente, registrarGestion, getTasaRecuperacion,
  getRutaHoy, registrarGestionRuta, getTimelineCliente, getEfectividadComercial, getPlanSemanal,
  getProximasAcciones,
} from '../services/cartera360';
import type { RegistrarGestionRequest, RegistrarGestionRutaRequest } from '../types/cartera360';
import { qk } from '../constants/queryKeys';
import { getApiErrorMessage as errorMessage } from '../utils/apiError';

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

// ── "Mi Ruta Inteligente de Ventas" ────────────────────────────────────────

export const useRutaHoy = () =>
  wrap(useQuery({
    queryKey: qk.ruta.hoy(),
    queryFn: () => getRutaHoy().then((r) => r.data),
  }));

export const useTimelineCliente = (clienteId: string | null) =>
  wrap(useQuery({
    queryKey: qk.ruta.timeline(clienteId ?? ''),
    queryFn: () => getTimelineCliente(clienteId as string).then((r) => r.data),
    enabled: !!clienteId,
  }));

export const useEfectividadComercial = () =>
  wrap(useQuery({
    queryKey: qk.ruta.efectividad(),
    queryFn: () => getEfectividadComercial().then((r) => r.data),
  }));

export const usePlanSemanal = () =>
  wrap(useQuery({
    queryKey: qk.ruta.planSemanal(),
    queryFn: () => getPlanSemanal().then((r) => r.data),
  }));

/** Auditoría 43 (H43-13): agenda propia del vendedor -- consumido por `UpcomingActions`,
 * antes derivaba (incorrectamente) de `useRutaHoy`, cuyo ranking excluye a estos mismos
 * clientes mientras la fecha siga vigente. */
export const useProximasAcciones = () =>
  wrap(useQuery({
    queryKey: qk.ruta.proximasAcciones(),
    queryFn: () => getProximasAcciones().then((r) => r.data),
  }));

export const useRegistrarGestionRuta = (clienteId: string | null) => {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (body: RegistrarGestionRutaRequest) => registrarGestionRuta(body).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.ruta.hoy() });
      queryClient.invalidateQueries({ queryKey: qk.ruta.efectividad() });
      // Auditoría 43 (H43-13): sin esto, registrar una "próxima acción" no producía
      // ningún efecto visible en su propio panel -- el "no funciona" reportado.
      queryClient.invalidateQueries({ queryKey: qk.ruta.proximasAcciones() });
      if (clienteId) queryClient.invalidateQueries({ queryKey: qk.ruta.timeline(clienteId) });
    },
  });
  return {
    execute: mutation.mutate,
    loading: mutation.isPending,
    error: errorMessage(mutation.error),
    isSuccess: mutation.isSuccess,
    reset: mutation.reset,
  };
};
