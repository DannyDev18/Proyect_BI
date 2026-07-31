import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const api = axios.create({
  baseURL: API_URL,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('auth_token');
    if (token) config.headers.Authorization = `Bearer ${token}`;
    return config;
  },
  (error) => Promise.reject(error)
);

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Auditoría 43 (H43-8..H43-10): un 401 significa que el token ya no sirve (expiró
      // o fue revocado por un logout) -- se limpia todo el estado de sesión, no solo el
      // token. `window.location.href` (no `navigate` de React Router) fuerza una recarga
      // completa de página, que por sí sola destruye la caché de TanStack Query y los
      // stores Zustand en memoria; lo que SÍ sobrevive a una recarga es lo persistido en
      // Web Storage, por eso se limpia explícitamente antes de redirigir.
      localStorage.removeItem('auth_token');
      localStorage.removeItem('auth_user');
      sessionStorage.clear();
      if (window.location.pathname !== '/login') window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);
