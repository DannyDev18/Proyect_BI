import { create } from 'zustand';

export type Role = 'administrador' | 'gerencia' | 'bodega' | 'ventas';

export interface User {
  id: string | number;
  name: string;
  email: string;
  role: Role;
  sucursalId?: string;
}

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  login: (user: User, token: string) => void;
  logout: () => void;
}

// Initial state from localStorage if available
const storedToken = localStorage.getItem('auth_token');
const storedUser = localStorage.getItem('auth_user');

export const useAuthStore = create<AuthState>((set) => ({
  user: storedUser ? JSON.parse(storedUser) : null,
  token: storedToken || null,
  isAuthenticated: !!storedToken,

  login: (user: User, token: string) => {
    localStorage.setItem('auth_token', token);
    localStorage.setItem('auth_user', JSON.stringify(user));
    set({ user, token, isAuthenticated: true });
  },

  logout: () => {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('auth_user');
    set({ user: null, token: null, isAuthenticated: false });
  },
}));
