import { api } from './http';
import type {
  BodegaKPIs,
  CategoriaSalidas,
  DemandaResponse,
  FiltrosBodega,
  InventarioMatriz,
  KpisBodega,
  NecesidadCompra,
  NotificacionBodega,
  PrediccionComprasMes,
  ProductoStockReorden,
  ProductoTopSalidas,
  ReporteBodega,
  RotacionMatriz,
  SalidasForecast,
  TipoReporteBodega,
  Transferencias,
} from '../types/bodega';
import type { Page, PaginationQuery } from '../types/pagination';

const BASE = '/api/v1/analytics/bodega';

/** Filtros globales del dashboard (§1.1) serializados como query params. */
export interface BodegaQueryFilters {
  almacen?: string | null;
  categoria?: string | null;
  proveedor?: string | null;
  busqueda?: string | null;
  fecha_desde?: string | null;
  fecha_hasta?: string | null;
}

const clean = (params: object) =>
  Object.fromEntries(Object.entries(params).filter(([, v]) => v !== null && v !== undefined && v !== ''));

// ── Legado ───────────────────────────────────────────────────────────────────
export const getBodegaKPIs = () =>
  api.get<BodegaKPIs>(`${BASE}/kpis-inventory`);

export const getDemandForecast = (producto_cod: string) =>
  api.get<DemandaResponse>(`${BASE}/demand-forecasting`, { params: { producto_cod } });

// ── Módulo Bodega (auditoría 23) ────────────────────────────────────────────
export const getBodegaFiltros = () =>
  api.get<FiltrosBodega>(`${BASE}/filtros`);

export const getKpisBodega = (filters: BodegaQueryFilters) =>
  api.get<KpisBodega>(`${BASE}/kpis`, { params: clean(filters) });

export const getSalidasForecast = (filters: BodegaQueryFilters, productoCod?: string | null) =>
  api.get<SalidasForecast>(`${BASE}/salidas-forecast`, {
    params: clean({ ...filters, busqueda: undefined, producto_cod: productoCod }),
  });

export const getRotacionMatriz = (filters: BodegaQueryFilters) =>
  api.get<RotacionMatriz>(`${BASE}/rotacion-matriz`, { params: clean(filters) });

export const getTopProductos = (filters: BodegaQueryFilters, limit = 20) =>
  api.get<ProductoTopSalidas[]>(`${BASE}/top-productos`, { params: clean({ ...filters, limit }) });

export const getSalidasCategoria = (filters: BodegaQueryFilters) =>
  api.get<CategoriaSalidas[]>(`${BASE}/salidas-categoria`, {
    params: clean({ ...filters, categoria: undefined }),
  });

export const getStockReorden = (filters: BodegaQueryFilters, soloCriticos: boolean, pagination: PaginationQuery) =>
  api.get<Page<ProductoStockReorden>>(`${BASE}/stock-reorden`, {
    params: clean({ ...filters, fecha_desde: undefined, fecha_hasta: undefined, solo_criticos: soloCriticos, ...pagination }),
  });

export const getNecesidadCompra = (filters: BodegaQueryFilters, horizonteDias: number | undefined, pagination: PaginationQuery) =>
  api.get<NecesidadCompra>(`${BASE}/necesidad-compra`, {
    params: clean({ ...filters, fecha_desde: undefined, fecha_hasta: undefined, horizonte_dias: horizonteDias, ...pagination }),
  });

export const getInventarioMatriz = (filters: BodegaQueryFilters, estado: string | null, pagination: PaginationQuery) =>
  api.get<InventarioMatriz>(`${BASE}/inventario-matriz`, {
    params: clean({
      categoria: filters.categoria, proveedor: filters.proveedor,
      busqueda: filters.busqueda, estado, ...pagination,
    }),
  });

export const getTransferenciasSugeridas = (filters: BodegaQueryFilters, pagination: PaginationQuery) =>
  api.get<Transferencias>(`${BASE}/transferencias-sugeridas`, {
    params: clean({ categoria: filters.categoria, proveedor: filters.proveedor, busqueda: filters.busqueda, ...pagination }),
  });

export const getPrediccionComprasMes = (filters: BodegaQueryFilters, productoCod?: string | null) =>
  api.get<PrediccionComprasMes>(`${BASE}/prediccion-compras-mes`, {
    params: clean({
      categoria: filters.categoria, almacen: filters.almacen, proveedor: filters.proveedor,
      producto_cod: productoCod,
    }),
  });

export const getNotificacionesBodega = (almacen?: string | null) =>
  api.get<NotificacionBodega[]>(`${BASE}/notificaciones`, { params: clean({ almacen }) });

export const getReporteBodega = (tipo: TipoReporteBodega, filters: BodegaQueryFilters) =>
  api.get<ReporteBodega>(`${BASE}/reportes/${tipo}`, {
    params: clean({
      almacen: filters.almacen, categoria: filters.categoria, proveedor: filters.proveedor,
    }),
  });

/** Descarga el XLSX del reporte (§2.1 "exportar a Excel para edición"). */
export const descargarReporteExcel = async (tipo: TipoReporteBodega, filters: BodegaQueryFilters) => {
  const res = await api.get<Blob>(`${BASE}/reportes/${tipo}/excel`, {
    params: clean({
      almacen: filters.almacen, categoria: filters.categoria, proveedor: filters.proveedor,
    }),
    responseType: 'blob',
  });
  const url = URL.createObjectURL(res.data);
  const link = document.createElement('a');
  link.href = url;
  link.download = `reporte_${tipo}.xlsx`;
  link.click();
  URL.revokeObjectURL(url);
};
