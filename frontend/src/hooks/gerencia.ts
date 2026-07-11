import { useQuery } from '@tanstack/react-query';
import {
  getGerenciaKPIs, getRevenueByCategory, getCategories, getSucursales, getVendedores, getAlmacenes, getSalesPrediction,
} from '../services/gerencia';
import { qk } from '../constants/queryKeys';

const errorMessage = (error: unknown): string | null =>
  error ? (error instanceof Error ? error.message : 'Error al cargar datos') : null;

type GerenciaKpiParams = Parameters<typeof getGerenciaKPIs>[0];
type RevenueByCategoryParams = Parameters<typeof getRevenueByCategory>[0];

export const useGerenciaKPIs = (params: GerenciaKpiParams = {}) => {
  const query = useQuery({
    queryKey: qk.gerencia.kpis(params),
    queryFn: () => getGerenciaKPIs(params).then((r) => r.data),
  });
  return { data: query.data ?? null, loading: query.isLoading, error: errorMessage(query.error), refetch: query.refetch };
};

export const useRevenueByCategory = (params: RevenueByCategoryParams = {}) => {
  const query = useQuery({
    queryKey: qk.gerencia.revenueByCategory(params),
    queryFn: () => getRevenueByCategory(params).then((r) => r.data),
  });
  return { data: query.data ?? null, loading: query.isLoading, error: errorMessage(query.error), refetch: query.refetch };
};

export const useCategories = () => {
  const query = useQuery({
    queryKey: qk.gerencia.categories(),
    queryFn: () => getCategories().then((r) => r.data),
  });
  return { data: query.data ?? null, loading: query.isLoading, error: errorMessage(query.error), refetch: query.refetch };
};

export const useSucursales = () => {
  const query = useQuery({
    queryKey: qk.gerencia.sucursales(),
    queryFn: () => getSucursales().then((r) => r.data),
  });
  return { data: query.data ?? null, loading: query.isLoading, error: errorMessage(query.error), refetch: query.refetch };
};

export const useVendedores = () => {
  const query = useQuery({
    queryKey: qk.gerencia.vendedores(),
    queryFn: () => getVendedores().then((r) => r.data),
  });
  return { data: query.data ?? null, loading: query.isLoading, error: errorMessage(query.error), refetch: query.refetch };
};

export const useAlmacenes = () => {
  const query = useQuery({
    queryKey: qk.gerencia.almacenes(),
    queryFn: () => getAlmacenes().then((r) => r.data),
  });
  return { data: query.data ?? null, loading: query.isLoading, error: errorMessage(query.error), refetch: query.refetch };
};

type SalesPredictionParams = Parameters<typeof getSalesPrediction>[0];

export const useSalesPrediction = (params: SalesPredictionParams) => {
  const query = useQuery({
    queryKey: qk.gerencia.salesPrediction(params),
    queryFn: () => getSalesPrediction(params).then((r) => r.data),
  });
  return { data: query.data ?? null, loading: query.isLoading, error: errorMessage(query.error), refetch: query.refetch };
};
