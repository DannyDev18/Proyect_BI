import { api } from './http';
import type {
  DetalleCliente,
  EfectividadComercial,
  ListaTrabajo,
  PlanSemanal,
  ProximasAcciones,
  RegistrarGestionRequest,
  RegistrarGestionResponse,
  RegistrarGestionRutaRequest,
  RegistrarGestionRutaResponse,
  RutaHoy,
  TasaRecuperacion,
  TimelineCliente,
} from '../types/cartera360';

const BASE = '/api/v1/analytics/ventas/cartera360';
const BASE_RUTA = '/api/v1/analytics/ventas/ruta';

export const getListaTrabajo = () =>
  api.get<ListaTrabajo>(`${BASE}/lista-trabajo`);

export const getDetalleCliente = (clienteId: string) =>
  api.get<DetalleCliente>(`${BASE}/clientes/${encodeURIComponent(clienteId)}/detalle`);

export const registrarGestion = (body: RegistrarGestionRequest) =>
  api.post<RegistrarGestionResponse>(`${BASE}/gestion`, body);

export const getTasaRecuperacion = () =>
  api.get<TasaRecuperacion>(`${BASE}/tasa-recuperacion`);

// ── "Mi Ruta Inteligente de Ventas" ────────────────────────────────────────

export const getRutaHoy = () =>
  api.get<RutaHoy>(`${BASE_RUTA}/hoy`);

export const registrarGestionRuta = (body: RegistrarGestionRutaRequest) =>
  api.post<RegistrarGestionRutaResponse>(`${BASE_RUTA}/gestion`, body);

export const getTimelineCliente = (clienteId: string) =>
  api.get<TimelineCliente>(`${BASE_RUTA}/clientes/${encodeURIComponent(clienteId)}/timeline`);

export const getEfectividadComercial = () =>
  api.get<EfectividadComercial>(`${BASE_RUTA}/efectividad`);

export const getPlanSemanal = () =>
  api.get<PlanSemanal>(`${BASE_RUTA}/plan-semanal`);

export const getProximasAcciones = () =>
  api.get<ProximasAcciones>(`${BASE_RUTA}/proximas-acciones`);
