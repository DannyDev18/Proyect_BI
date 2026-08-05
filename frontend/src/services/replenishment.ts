import { api } from './http';
import type {
  AlertaReabastecimiento,
  CrearPropuestaRequest,
  ItemReabastecimiento,
  LeadTimeConfig,
  PoliticaABC,
  PropuestaCompra,
  PropuestaCompraDetalle,
  ResumenReabastecimiento,
  SimularReabastecimientoRequest,
  SimularReabastecimientoResponse,
} from '../types/replenishment';
import type { Page, PaginationQuery } from '../types/pagination';
import type { BodegaQueryFilters } from './bodega';

const BASE = '/api/v1/analytics/bodega/reabastecimiento';

const clean = (params: object) =>
  Object.fromEntries(Object.entries(params).filter(([, v]) => v !== null && v !== undefined && v !== ''));

/** Filtros propios del Bloque 2 (Lista Inteligente), además de los globales de Bodega. */
export interface ReabastecimientoFiltrosExtra {
  horizonte_dias?: number | null;
  solo_criticos?: boolean;
  riesgo?: string | null;
  clase_abc?: string | null;
  clase_xyz?: string | null;
}

export const getListaReabastecimiento = (
  filters: BodegaQueryFilters, extra: ReabastecimientoFiltrosExtra, pagination: PaginationQuery,
) =>
  api.get<Page<ItemReabastecimiento>>(`${BASE}/lista`, {
    params: clean({
      almacen: filters.almacen, categoria: filters.categoria, proveedor: filters.proveedor,
      tipo_movimiento: filters.tipo_movimiento, ...extra, ...pagination,
    }),
  });

export const getResumenReabastecimiento = (
  filters: BodegaQueryFilters, horizonteDias?: number | null,
) =>
  api.get<ResumenReabastecimiento>(`${BASE}/resumen`, {
    params: clean({
      almacen: filters.almacen, categoria: filters.categoria, proveedor: filters.proveedor,
      tipo_movimiento: filters.tipo_movimiento, horizonte_dias: horizonteDias,
    }),
  });

// ── Configuración editable (§6.3, solo gerencia/administrador) ─────────────────────
export const getPoliticaABC = () =>
  api.get<PoliticaABC[]>(`${BASE}/politica`);

export const updatePoliticaABC = (claseAbc: string, nivelServicio: number) =>
  api.put<PoliticaABC>(`${BASE}/politica/${claseAbc}`, { nivel_servicio: nivelServicio });

export const getLeadTimes = () =>
  api.get<LeadTimeConfig[]>(`${BASE}/lead-times`);

export const upsertLeadTime = (
  dias: number, target: { producto?: string | null; categoria?: string | null; proveedor?: string | null },
) =>
  api.put<LeadTimeConfig>(`${BASE}/lead-times`, { dias, ...target });

export const deleteLeadTime = (leadTimeId: number) =>
  api.delete<void>(`${BASE}/lead-times/${leadTimeId}`);

// ── F7: Alertas inteligentes ─────────────────────────────────────────────────────
export const getAlertasReabastecimiento = (filters: BodegaQueryFilters, horizonteDias?: number | null) =>
  api.get<AlertaReabastecimiento[]>(`${BASE}/alertas`, {
    params: clean({
      almacen: filters.almacen, categoria: filters.categoria, proveedor: filters.proveedor,
      tipo_movimiento: filters.tipo_movimiento, horizonte_dias: horizonteDias,
    }),
  });

// ── F8: Simulador what-if (solo lectura, no persiste) ────────────────────────────
export const simularReabastecimiento = (body: SimularReabastecimientoRequest) =>
  api.post<SimularReabastecimientoResponse>(`${BASE}/simular`, body);

// ── F9: propuestas de compra persistidas (bloque 5, Gestión Operativa) ───────────
export const crearPropuestaCompra = (body: CrearPropuestaRequest) =>
  api.post<PropuestaCompraDetalle>(`${BASE}/propuestas`, body);

export const getPropuestasCompra = () =>
  api.get<PropuestaCompra[]>(`${BASE}/propuestas`);

export const getPropuestaCompraDetalle = (id: number) =>
  api.get<PropuestaCompraDetalle>(`${BASE}/propuestas/${id}`);

export const aprobarPropuestaCompra = (id: number) =>
  api.post<PropuestaCompra>(`${BASE}/propuestas/${id}/aprobar`);

export const rechazarPropuestaCompra = (id: number) =>
  api.post<PropuestaCompra>(`${BASE}/propuestas/${id}/rechazar`);
