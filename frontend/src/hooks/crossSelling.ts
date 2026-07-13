import { useMutation, useQuery } from '@tanstack/react-query';
import {
  getCrossSellKpis,
  getCrossSellSugerencias,
  getCrossSellTopCombinaciones,
  postCrossSellEvento,
  searchClientes,
  searchProductos,
} from '../services/crossSelling';
import { qk } from '../constants/queryKeys';

const errorMessage = (error: unknown): string | null =>
  error ? (error instanceof Error ? error.message : 'Error al cargar datos') : null;

const wrap = <T,>(query: { data?: T; isLoading: boolean; error: unknown; refetch: () => unknown }) => ({
  data: query.data ?? null,
  loading: query.isLoading,
  error: errorMessage(query.error),
  refetch: query.refetch,
});

export const useCrossSellSugerencias = (items: string[], clienteId: string | null) =>
  wrap(useQuery({
    queryKey: qk.crossSelling.sugerencias(items, clienteId),
    queryFn: () => getCrossSellSugerencias(items, clienteId).then((r) => r.data),
    enabled: items.length > 0,
  }));

export const useCrossSellEvento = () => useMutation({ mutationFn: postCrossSellEvento });

export const useCrossSellKpis = (desde?: string, hasta?: string) =>
  wrap(useQuery({
    queryKey: qk.crossSelling.kpis(desde, hasta),
    queryFn: () => getCrossSellKpis(desde, hasta).then((r) => r.data),
  }));

export const useCrossSellTopCombinaciones = () =>
  wrap(useQuery({
    queryKey: qk.crossSelling.topCombinaciones(),
    queryFn: () => getCrossSellTopCombinaciones().then((r) => r.data),
  }));

export const useSearchProductos = (q: string) =>
  wrap(useQuery({
    queryKey: qk.crossSelling.productos(q),
    queryFn: () => searchProductos(q).then((r) => r.data),
    enabled: q.trim().length >= 2,
  }));

export const useSearchClientes = (q: string) =>
  wrap(useQuery({
    queryKey: qk.crossSelling.clientes(q),
    queryFn: () => searchClientes(q).then((r) => r.data),
    enabled: q.trim().length >= 2,
  }));
