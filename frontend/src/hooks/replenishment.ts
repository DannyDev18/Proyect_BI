import { useMutation, useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query';
import {
  aprobarPropuestaCompra,
  crearPropuestaCompra,
  deleteLeadTime,
  getAlertasReabastecimiento,
  getLeadTimes,
  getListaReabastecimiento,
  getPoliticaABC,
  getPropuestaCompraDetalle,
  getPropuestasCompra,
  getResumenReabastecimiento,
  rechazarPropuestaCompra,
  simularReabastecimiento,
  updatePoliticaABC,
  upsertLeadTime,
  type ReabastecimientoFiltrosExtra,
} from '../services/replenishment';
import type { BodegaQueryFilters } from '../services/bodega';
import type { PaginationQuery } from '../types/pagination';
import type { CrearPropuestaRequest, SimularReabastecimientoRequest } from '../types/replenishment';
import { qk } from '../constants/queryKeys';
import { getApiErrorMessage as errorMessage } from '../utils/apiError';

const wrap = <T,>(query: { data?: T; isLoading: boolean; error: unknown; refetch: () => unknown }) => ({
  data: query.data ?? null,
  loading: query.isLoading,
  error: errorMessage(query.error),
  refetch: query.refetch,
});

export const useListaReabastecimiento = (
  filters: BodegaQueryFilters, extra: ReabastecimientoFiltrosExtra, pagination: PaginationQuery,
) =>
  wrap(useQuery({
    queryKey: qk.reabastecimiento.lista(filters, extra, pagination),
    queryFn: () => getListaReabastecimiento(filters, extra, pagination).then((r) => r.data),
    placeholderData: keepPreviousData,
  }));

export const useResumenReabastecimiento = (filters: BodegaQueryFilters, horizonteDias?: number | null) =>
  wrap(useQuery({
    queryKey: qk.reabastecimiento.resumen(filters, horizonteDias),
    queryFn: () => getResumenReabastecimiento(filters, horizonteDias).then((r) => r.data),
  }));

export const usePoliticaABC = () =>
  wrap(useQuery({
    queryKey: qk.reabastecimiento.politica(),
    queryFn: () => getPoliticaABC().then((r) => r.data),
  }));

export const useLeadTimes = () =>
  wrap(useQuery({
    queryKey: qk.reabastecimiento.leadTimes(),
    queryFn: () => getLeadTimes().then((r) => r.data),
  }));

export const useUpdatePoliticaABC = () => {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: ({ claseAbc, nivelServicio }: { claseAbc: string; nivelServicio: number }) =>
      updatePoliticaABC(claseAbc, nivelServicio).then((r) => r.data),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['reabastecimiento'] }); },
  });
  return {
    mutate: mutation.mutate,
    loading: mutation.isPending,
    error: errorMessage(mutation.error),
  };
};

export const useUpsertLeadTime = () => {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (
      { dias, ...target }: { dias: number; producto?: string | null; categoria?: string | null; proveedor?: string | null },
    ) => upsertLeadTime(dias, target).then((r) => r.data),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['reabastecimiento'] }); },
  });
  return {
    mutate: mutation.mutate,
    loading: mutation.isPending,
    error: errorMessage(mutation.error),
  };
};

export const useAlertasReabastecimiento = (filters: BodegaQueryFilters, horizonteDias?: number | null) =>
  wrap(useQuery({
    queryKey: qk.reabastecimiento.alertas(filters, horizonteDias),
    queryFn: () => getAlertasReabastecimiento(filters, horizonteDias).then((r) => r.data),
  }));

export const useSimularReabastecimiento = () => {
  const mutation = useMutation({
    mutationFn: (body: SimularReabastecimientoRequest) => simularReabastecimiento(body).then((r) => r.data),
  });
  return {
    data: mutation.data ?? null,
    loading: mutation.isPending,
    error: errorMessage(mutation.error),
    simular: (body: SimularReabastecimientoRequest) => { mutation.reset(); mutation.mutate(body); },
  };
};

export const useDeleteLeadTime = () => {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (leadTimeId: number) => deleteLeadTime(leadTimeId),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['reabastecimiento'] }); },
  });
  return {
    mutate: mutation.mutate,
    loading: mutation.isPending,
    error: errorMessage(mutation.error),
  };
};

// ── F9: propuestas de compra persistidas ──────────────────────────────────────────
export const usePropuestasCompra = () =>
  wrap(useQuery({
    queryKey: qk.reabastecimiento.propuestas(),
    queryFn: () => getPropuestasCompra().then((r) => r.data),
  }));

export const usePropuestaCompraDetalle = (id: number | null) =>
  wrap(useQuery({
    queryKey: qk.reabastecimiento.propuestaDetalle(id ?? -1),
    queryFn: () => getPropuestaCompraDetalle(id as number).then((r) => r.data),
    enabled: id != null,
  }));

export const useCrearPropuestaCompra = () => {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (body: CrearPropuestaRequest) => crearPropuestaCompra(body).then((r) => r.data),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: qk.reabastecimiento.propuestas() }); },
  });
  return {
    data: mutation.data ?? null,
    loading: mutation.isPending,
    error: errorMessage(mutation.error),
    crear: (body: CrearPropuestaRequest) => { mutation.reset(); mutation.mutate(body); },
  };
};

export const useDecidirPropuestaCompra = () => {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: ({ id, decision }: { id: number; decision: 'aprobar' | 'rechazar' }) =>
      (decision === 'aprobar' ? aprobarPropuestaCompra(id) : rechazarPropuestaCompra(id)).then((r) => r.data),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: qk.reabastecimiento.propuestas() }); },
  });
  return {
    mutate: mutation.mutate,
    loading: mutation.isPending,
    error: errorMessage(mutation.error),
  };
};
