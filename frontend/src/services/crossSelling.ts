import { api } from './http';
import type {
  CrossSellEventoRequest,
  CrossSellKpis,
  CrossSellSugerenciasResponse,
  ProductoBusqueda,
} from '../types/crossSelling';

const BASE = '/api/v1/analytics/ventas/cross-selling';

export const getCrossSellSugerencias = (items: string[], clienteId?: string | null, topN?: number) =>
  api.post<CrossSellSugerenciasResponse>(`${BASE}/sugerencias`, {
    items,
    cliente_id: clienteId || null,
    top_n: topN,
  });

export const postCrossSellEvento = (payload: CrossSellEventoRequest) =>
  api.post(`${BASE}/eventos`, payload);

export const getCrossSellKpis = (desde?: string, hasta?: string) =>
  api.get<CrossSellKpis>(`${BASE}/kpis`, { params: { desde, hasta } });

export const searchProductos = (q: string) =>
  api.get<ProductoBusqueda[]>(`${BASE}/productos`, { params: { q } });
