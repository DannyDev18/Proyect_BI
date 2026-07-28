import { keepPreviousData, useMutation, useQuery } from '@tanstack/react-query';
import {
  getCrossSellCombos,
  getCrossSellKpis,
  getCrossSellSugerencias,
  getExplicacionChurn,
  getPerfilCliente,
  postCrossSellEvento,
  searchClientes,
  searchProductos,
  simularVenta,
} from '../services/crossSelling';
import { qk } from '../constants/queryKeys';
import { useDebouncedValue } from './useDebouncedValue';

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

export const usePerfilCliente = (clienteId: string | null) =>
  wrap(useQuery({
    queryKey: qk.crossSelling.perfilCliente(clienteId),
    queryFn: () => getPerfilCliente(clienteId as string).then((r) => r.data),
    enabled: !!clienteId,
  }));

/** Fase 3 (docs/features/plan_refactor_venta_cruzada_ia.md §3 punto 2): recálculo en
 * vivo con cada cambio de canasta, debounced (evita una llamada por tecla/clic) y con
 * `keepPreviousData` para que las cifras no parpadeen a vacío entre un cambio y el
 * siguiente. */
export const useCrossSellCombos = (clienteId: string | null) =>
  wrap(useQuery({
    queryKey: qk.crossSelling.combos(clienteId),
    queryFn: () => getCrossSellCombos(clienteId).then((r) => r.data),
  }));

/** Fase 6 (§2.1 Opción A): explicación real (SHAP) bajo demanda -- `enabled` solo
 * cuando el panel "¿Por qué esto?" se abre, no en cada carga del perfil. */
export const useExplicacionChurn = (clienteId: string | null, habilitado: boolean) =>
  wrap(useQuery({
    queryKey: qk.crossSelling.explicacionChurn(clienteId),
    queryFn: () => getExplicacionChurn(clienteId as string).then((r) => r.data),
    enabled: !!clienteId && habilitado,
  }));

export const useSimularVenta = (items: string[], clienteId: string | null) => {
  const itemsDebounced = useDebouncedValue(items, 400);
  return wrap(useQuery({
    queryKey: qk.crossSelling.simular(itemsDebounced, clienteId),
    queryFn: () => simularVenta(itemsDebounced, clienteId).then((r) => r.data),
    enabled: itemsDebounced.length > 0,
    placeholderData: keepPreviousData,
  }));
};
