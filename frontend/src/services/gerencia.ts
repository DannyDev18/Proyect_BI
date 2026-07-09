import { api } from './http';
import type { GerenciaKPIs, SalesPredictionResponse } from '../types/gerencia';

interface DateRangeParams {
  start_date?: string;
  end_date?: string;
}

const cleanParams = <T extends object>(params?: T): Partial<T> | undefined => {
  if (!params) return undefined;
  const cleaned: Record<string, unknown> = {};
  const dateRegex = /^\d{4}-\d{2}-\d{2}$/;
  for (const [key, value] of Object.entries(params)) {
    if (value === '' || value === null || value === undefined) {
      continue;
    }
    if ((key === 'start_date' || key === 'end_date') && typeof value === 'string') {
      if (dateRegex.test(value)) {
        cleaned[key] = value;
      }
    } else {
      cleaned[key] = value;
    }
  }
  return cleaned as Partial<T>;
};

export const getGerenciaKPIs = (params?: DateRangeParams & { categoria?: string; sucursal?: string; vendedor?: string }) =>
  api.get<GerenciaKPIs>('/api/v1/analytics/gerencia/kpis', { params: cleanParams(params) });

export const getRevenueByCategory = (params?: DateRangeParams & { sucursal?: string; vendedor?: string }) =>
  api.get<{ cat: string, v: number }[]>('/api/v1/analytics/gerencia/revenue-by-category', { params: cleanParams(params) });

export const getCategories = () =>
  api.get<string[]>('/api/v1/analytics/gerencia/categorias');

export const getSucursales = () =>
  api.get<string[]>('/api/v1/analytics/gerencia/sucursales');

export const getVendedores = () =>
  api.get<string[]>('/api/v1/analytics/gerencia/vendedores');

export const getSalesPrediction = () =>
  api.get<SalesPredictionResponse>('/api/v1/analytics/gerencia/sales-prediction');
