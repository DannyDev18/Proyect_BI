import { useQuery } from '@tanstack/react-query';
import {
  getCumplimientoMetaPeriodo, getGerenciaKPIs, getRevenueByCategory, getCategories, getSucursales, getVendedores,
  getAlmacenes, getEvolucionMensualVentas,
} from '../services/gerencia';
import { qk } from '../constants/queryKeys';
import { getApiErrorMessage as errorMessage } from '../utils/apiError';

type GerenciaKpiParams = Parameters<typeof getGerenciaKPIs>[0];
type RevenueByCategoryParams = Parameters<typeof getRevenueByCategory>[0];

export const useGerenciaKPIs = (params: GerenciaKpiParams = {}) => {
  const query = useQuery({
    queryKey: qk.gerencia.kpis(params),
    queryFn: () => getGerenciaKPIs(params).then((r) => r.data),
  });
  return { data: query.data ?? null, loading: query.isLoading, error: errorMessage(query.error), refetch: query.refetch };
};

// Fase 2 Gerencia (docs/features/plan_correcciones_pendientes.md §3): KPI de
// cumplimiento vs metas del período en el dashboard principal.
export const useCumplimientoMeta = (anio: number, mes: number) => {
  const query = useQuery({
    queryKey: qk.gerencia.cumplimientoMeta(anio, mes),
    queryFn: () => getCumplimientoMetaPeriodo(anio, mes).then((r) => r.data),
  });
  return { data: query.data ?? null, loading: query.isLoading, error: errorMessage(query.error) };
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

type EvolucionMensualVentasParams = Parameters<typeof getEvolucionMensualVentas>[0];

// Reemplaza a useSalesPrediction (auditoría 49, decomisión de `sales_rf`): histórico
// real mes a mes, sin ningún modelo.
export const useEvolucionMensualVentas = (params?: EvolucionMensualVentasParams) => {
  const query = useQuery({
    queryKey: qk.gerencia.evolucionMensual(params),
    queryFn: () => getEvolucionMensualVentas(params).then((r) => r.data.serie),
  });
  return { data: query.data ?? null, loading: query.isLoading, error: errorMessage(query.error), refetch: query.refetch };
};
