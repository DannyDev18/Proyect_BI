import { useState, useEffect, useCallback } from 'react';
import {
  getGerenciaKPIs, getSalesPrediction, getRevenueByCategory, getCategories,
  getBodegaKPIs, getDemandForecast, getSucursales, getVendedores,
  getSalesGoals, getChurnRisk, getRecommendations, getCustomerSegment,
  detectAnomaly,
  type GerenciaKPIs, type SalesPredictionResponse, type BodegaKPIs,
  type DemandaResponse, type VentasKPIs, type ChurnResponse,
  type RecomendacionResponse, type SegmentacionResponse, type AnomaliaResponse,
} from '../services/api';

// ─── Generic async hook factory ──────────────────────────────────────────────
function useAsync<T>(fn: () => Promise<{ data: T }>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const execute = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fn();
      setData(res.data);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error al cargar datos';
      setError(msg);
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => { execute(); }, [execute]);
  return { data, loading, error, refetch: execute };
}

// ─── Async hook factory for on-demand (parametric) queries ───────────────────
function useAsyncParam<T, P>(fn: (param: P) => Promise<{ data: T }>) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const execute = useCallback(async (param: P) => {
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const res = await fn(param);
      setData(res.data);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error al cargar datos';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [fn]);

  return { data, loading, error, execute };
}

// ─── Gerencia ─────────────────────────────────────────────────────────────────
export const useGerenciaKPIs = (params: any = {}) =>
  useAsync<GerenciaKPIs>(() => getGerenciaKPIs(params), [JSON.stringify(params)]);

export const useRevenueByCategory = (params: any = {}) =>
  useAsync<{cat: string, v: number}[]>(() => getRevenueByCategory(params), [JSON.stringify(params)]);

export const useCategories = () =>
  useAsync<string[]>(getCategories, []);

export const useSucursales = () =>
  useAsync<string[]>(getSucursales, []);

export const useVendedores = () =>
  useAsync<string[]>(getVendedores, []);

export const useSalesPrediction = () =>
  useAsync<SalesPredictionResponse>(getSalesPrediction);

// ─── Bodega ───────────────────────────────────────────────────────────────────
export const useBodegaKPIs = () =>
  useAsync<BodegaKPIs>(getBodegaKPIs);

export const useDemandForecast = () =>
  useAsyncParam<DemandaResponse, string>((cod) => getDemandForecast(cod));

// ─── Ventas ───────────────────────────────────────────────────────────────────
export const useSalesGoals = () =>
  useAsync<VentasKPIs>(getSalesGoals);

export const useChurnRisk = () =>
  useAsyncParam<ChurnResponse, string>((id) => getChurnRisk(id));

export const useRecommendations = () =>
  useAsyncParam<RecomendacionResponse, string>((id) => getRecommendations(id));

export const useCustomerSegment = () =>
  useAsyncParam<SegmentacionResponse, string>((cod) => getCustomerSegment(cod));

// ─── Admin ────────────────────────────────────────────────────────────────────
export const useAnomalyDetector = () =>
  useAsyncParam<AnomaliaResponse, string>((id) => detectAnomaly(id));
