import { api } from './http';
import type { UserData, UserPayload } from '../types/admin';
import type { Page, PaginationQuery } from '../types/pagination';

export const getRoles = () =>
  api.get('/api/v1/roles/');

/** Fase 5 §5.1 (docs/features/plan_correcciones_integrales_sistema.md): paginación
 * real vía `Page[UserOut]`, mismo contrato que Bodega/Notificaciones -- antes devolvía
 * la lista completa sin paginar. */
export const getUsers = (pagination: PaginationQuery) =>
  api.get<Page<UserData>>('/api/v1/users/', { params: pagination });

export const getAlmacenes = () =>
  api.get('/api/v1/users/catalogos/almacenes');

export const createUser = (data: UserPayload) =>
  api.post('/api/v1/users/', data);

export const updateUser = (id: number, data: Partial<UserPayload>) =>
  api.put(`/api/v1/users/${id}`, data);

export const deactivateUser = (id: number) =>
  api.delete(`/api/v1/users/${id}`);

/** Borrado duro real (Fase 5 §5.3) -- distinto de `deactivateUser` (baja lógica).
 * El backend exige que el frontend ya haya obtenido consentimiento explícito antes de
 * llamar esto; no hay una segunda confirmación en la API. */
export const deleteUserPermanente = (id: number) =>
  api.delete(`/api/v1/users/${id}/permanente`);

export const activateUser = (id: number) =>
  api.post(`/api/v1/users/${id}/activate`);
