import { api } from './http';
import type {
  DetalleCliente,
  ListaTrabajo,
  RegistrarGestionRequest,
  RegistrarGestionResponse,
  TasaRecuperacion,
} from '../types/cartera360';

const BASE = '/api/v1/analytics/ventas/cartera360';

export const getListaTrabajo = () =>
  api.get<ListaTrabajo>(`${BASE}/lista-trabajo`);

export const getDetalleCliente = (clienteId: string) =>
  api.get<DetalleCliente>(`${BASE}/clientes/${encodeURIComponent(clienteId)}/detalle`);

export const registrarGestion = (body: RegistrarGestionRequest) =>
  api.post<RegistrarGestionResponse>(`${BASE}/gestion`, body);

export const getTasaRecuperacion = () =>
  api.get<TasaRecuperacion>(`${BASE}/tasa-recuperacion`);
