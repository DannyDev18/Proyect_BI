import { api } from './http';
import type {
  ChurnExplicacion,
  ClienteBusqueda,
  CombinacionInteligente,
  CrossSellEventoRequest,
  CrossSellKpis,
  CrossSellSugerenciasResponse,
  PerfilCliente,
  ProductoBusqueda,
  SimulacionVenta,
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

export const searchClientes = (q: string) =>
  api.get<ClienteBusqueda[]>(`${BASE}/clientes`, { params: { q } });

export const getPerfilCliente = (clienteId: string) =>
  api.get<PerfilCliente>(`${BASE}/clientes/${clienteId}/perfil`);

export const simularVenta = (items: string[], clienteId?: string | null) =>
  api.post<SimulacionVenta>(`${BASE}/simular`, { items, cliente_id: clienteId || null });

export const getCrossSellCombos = (clienteId?: string | null) =>
  api.get<{ combinaciones: CombinacionInteligente[] }>(`${BASE}/combos`, { params: { cliente_id: clienteId || undefined } });

export const getExplicacionChurn = (clienteId: string) =>
  api.get<ChurnExplicacion>(`${BASE}/clientes/${clienteId}/explicacion-churn`);
