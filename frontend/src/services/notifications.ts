import { api } from './http';
import type { Notificacion } from '../types/notifications';
import type { Page, PaginationQuery } from '../types/pagination';

const BASE = '/api/v1/notificaciones';

const clean = (params: Record<string, unknown>) =>
  Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== null));

export const getNotificaciones = () => api.get<Notificacion[]>(BASE);

export const marcarNotificacionLeida = (id: number) =>
  api.post<{ id: number; leida: boolean }>(`${BASE}/${id}/leer`);

export const marcarTodasLeidas = () => api.post<{ marcadas: number }>(`${BASE}/leer-todas`);

export const getHistorialNotificaciones = (pagination: PaginationQuery) =>
  api.get<Page<Notificacion>>(`${BASE}/historial`, { params: clean({ ...pagination }) });
