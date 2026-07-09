import { api } from './http';

export const authLogin = (email: string, password: string) =>
  api.post('/api/v1/auth/login', { username: email, password }, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
  });

export const getMe = () =>
  api.get('/api/v1/users/me');
