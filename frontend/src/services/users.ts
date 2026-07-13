import { api } from './http';
import type { UserPayload } from '../types/admin';

export const getRoles = () =>
  api.get('/api/v1/roles/');

export const getUsers = () =>
  api.get('/api/v1/users/');

export const getAlmacenes = () =>
  api.get('/api/v1/users/catalogos/almacenes');

export const createUser = (data: UserPayload) =>
  api.post('/api/v1/users/', data);

export const updateUser = (id: number, data: Partial<UserPayload>) =>
  api.put(`/api/v1/users/${id}`, data);

export const deactivateUser = (id: number) =>
  api.delete(`/api/v1/users/${id}`);

export const activateUser = (id: number) =>
  api.post(`/api/v1/users/${id}/activate`);
