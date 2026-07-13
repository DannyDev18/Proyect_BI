import { useQuery, useMutation, keepPreviousData } from '@tanstack/react-query';
import {
  getBodegaKPIs,
  getDemandForecast,
  getBodegaFiltros,
  getKpisBodega,
  getSalidasForecast,
  getRotacionMatriz,
  getTopProductos,
  getSalidasCategoria,
  getStockReorden,
  getNecesidadCompra,
  getInventarioMatriz,
  getTransferenciasSugeridas,
  getNotificacionesBodega,
  getReporteBodega,
  getPrediccionComprasMes,
  type BodegaQueryFilters,
} from '../services/bodega';
import type { TipoReporteBodega } from '../types/bodega';
import type { PaginationQuery } from '../types/pagination';
import { qk } from '../constants/queryKeys';

const errorMessage = (error: unknown): string | null =>
  error ? (error instanceof Error ? error.message : 'Error al cargar datos') : null;

const wrap = <T,>(query: { data?: T; isLoading: boolean; error: unknown; refetch: () => unknown }) => ({
  data: query.data ?? null,
  loading: query.isLoading,
  error: errorMessage(query.error),
  refetch: query.refetch,
});

// ── Legado ───────────────────────────────────────────────────────────────────
export const useBodegaKPIs = () =>
  wrap(useQuery({ queryKey: qk.bodega.kpis(), queryFn: () => getBodegaKPIs().then((r) => r.data) }));

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

// ── Módulo Bodega (auditoría 23) ────────────────────────────────────────────
export const useBodegaFiltros = () =>
  wrap(useQuery({
    queryKey: qk.bodega.filtros(),
    queryFn: () => getBodegaFiltros().then((r) => r.data),
    staleTime: 5 * 60 * 1000,
  }));

export const useKpisBodega = (filters: BodegaQueryFilters) =>
  wrap(useQuery({
    queryKey: qk.bodega.kpisDashboard(filters),
    queryFn: () => getKpisBodega(filters).then((r) => r.data),
  }));

export const useSalidasForecast = (filters: BodegaQueryFilters, productoCod: string | null) =>
  wrap(useQuery({
    queryKey: qk.bodega.salidasForecast(filters, productoCod),
    queryFn: () => getSalidasForecast(filters, productoCod).then((r) => r.data),
  }));

export const useRotacionMatriz = (filters: BodegaQueryFilters) =>
  wrap(useQuery({
    queryKey: qk.bodega.rotacionMatriz(filters),
    queryFn: () => getRotacionMatriz(filters).then((r) => r.data),
  }));

export const useTopProductos = (filters: BodegaQueryFilters, limit = 20) =>
  wrap(useQuery({
    queryKey: qk.bodega.topProductos({ ...filters, limit }),
    queryFn: () => getTopProductos(filters, limit).then((r) => r.data),
  }));

export const useSalidasCategoria = (filters: BodegaQueryFilters) =>
  wrap(useQuery({
    queryKey: qk.bodega.salidasCategoria(filters),
    queryFn: () => getSalidasCategoria(filters).then((r) => r.data),
  }));

export const useStockReorden = (filters: BodegaQueryFilters, soloCriticos: boolean, pagination: PaginationQuery) =>
  wrap(useQuery({
    queryKey: qk.bodega.stockReorden(filters, soloCriticos, pagination),
    queryFn: () => getStockReorden(filters, soloCriticos, pagination).then((r) => r.data),
    placeholderData: keepPreviousData,
  }));

export const useNecesidadCompra = (filters: BodegaQueryFilters, horizonteDias: number | undefined, pagination: PaginationQuery) =>
  wrap(useQuery({
    queryKey: qk.bodega.necesidadCompra(filters, horizonteDias, pagination),
    queryFn: () => getNecesidadCompra(filters, horizonteDias, pagination).then((r) => r.data),
    placeholderData: keepPreviousData,
  }));

export const useInventarioMatriz = (filters: BodegaQueryFilters, estado: string | null, pagination: PaginationQuery) =>
  wrap(useQuery({
    queryKey: qk.bodega.inventarioMatriz(filters, estado, pagination),
    queryFn: () => getInventarioMatriz(filters, estado, pagination).then((r) => r.data),
    placeholderData: keepPreviousData,
  }));

export const useTransferenciasSugeridas = (filters: BodegaQueryFilters, pagination: PaginationQuery) =>
  wrap(useQuery({
    queryKey: qk.bodega.transferencias(filters, pagination),
    queryFn: () => getTransferenciasSugeridas(filters, pagination).then((r) => r.data),
    placeholderData: keepPreviousData,
  }));

export const usePrediccionComprasMes = (filters: BodegaQueryFilters, productoCod: string | null) =>
  wrap(useQuery({
    queryKey: qk.bodega.prediccionComprasMes(filters, productoCod),
    queryFn: () => getPrediccionComprasMes(filters, productoCod).then((r) => r.data),
    staleTime: 30 * 60 * 1000, // 30 min: 20 walk-forward por request, no repetir al alternar drill-downs
  }));

export const useNotificacionesBodega = (almacen: string | null, enabled = true) =>
  wrap(useQuery({
    queryKey: qk.bodega.notificaciones(almacen),
    queryFn: () => getNotificacionesBodega(almacen).then((r) => r.data),
    refetchInterval: 5 * 60 * 1000, // la campana se refresca sola cada 5 minutos
    enabled,
  }));

export const useReporteBodega = (tipo: TipoReporteBodega, filters: BodegaQueryFilters, enabled = true) =>
  wrap(useQuery({
    queryKey: qk.bodega.reporte(tipo, filters),
    queryFn: () => getReporteBodega(tipo, filters).then((r) => r.data),
    enabled,
  }));
