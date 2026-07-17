import { api } from './http';
import type {
  CumplimientoMetaPeriodo, GerenciaKPIs, SalesPredictionGranularidad, SalesPredictionResponse,
} from '../types/gerencia';

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

export const getGerenciaKPIs = (params?: DateRangeParams & { categoria?: string; sucursal?: string; vendedor?: string; almacen?: string }) =>
  api.get<GerenciaKPIs>('/api/v1/analytics/gerencia/kpis', { params: cleanParams(params) });

export const getCumplimientoMetaPeriodo = (anio: number, mes: number) =>
  api.get<CumplimientoMetaPeriodo>('/api/v1/gerencia/goals/cumplimiento', { params: { anio, mes } });

// Fase 2 Gerencia (docs/features/plan_correcciones_pendientes.md §3): export del
// dashboard -- mismo patrón que descargarReporteExcel de Bodega (services/bodega.ts).
export const descargarReporteDashboardExcel = async (
  params?: DateRangeParams & { categoria?: string; sucursal?: string; vendedor?: string; almacen?: string },
) => {
  const res = await api.get<Blob>('/api/v1/analytics/gerencia/reportes/dashboard/excel', {
    params: cleanParams(params),
    responseType: 'blob',
  });
  const url = URL.createObjectURL(res.data);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'reporte_dashboard_gerencial.xlsx';
  link.click();
  URL.revokeObjectURL(url);
};

export const getRevenueByCategory = (params?: DateRangeParams & { sucursal?: string; vendedor?: string; almacen?: string }) =>
  api.get<{ cat: string, v: number }[]>('/api/v1/analytics/gerencia/revenue-by-category', { params: cleanParams(params) });

export const getCategories = () =>
  api.get<string[]>('/api/v1/analytics/gerencia/categorias');

export const getSucursales = () =>
  api.get<string[]>('/api/v1/analytics/gerencia/sucursales');

export const getVendedores = () =>
  api.get<string[]>('/api/v1/analytics/gerencia/vendedores');

export const getAlmacenes = () =>
  api.get<string[]>('/api/v1/analytics/gerencia/almacenes');

export const getSalesPrediction = (params: {
  granularidad: SalesPredictionGranularidad;
  vendedor?: string;
  almacen?: string;
}) =>
  api.get<SalesPredictionResponse>('/api/v1/analytics/gerencia/sales-prediction', { params: cleanParams(params) });
