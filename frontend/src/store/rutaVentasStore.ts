import { create } from 'zustand';

interface RutaVentasStore {
  /** Cliente cuya tarjeta de la ruta está abierta en el Drawer (gestión + timeline). Sin `persist`: trae PII real (nombre), mismo criterio que `crossSellStore`. */
  clienteAbiertoId: string | null;
  abrirCliente: (clienteId: string) => void;
  cerrarCliente: () => void;
  /** Auditoría 43 (H43-9): invocado desde el cierre de sesión. */
  reset: () => void;
}

export const useRutaVentasStore = create<RutaVentasStore>((set) => ({
  clienteAbiertoId: null,
  abrirCliente: (clienteId) => set({ clienteAbiertoId: clienteId }),
  cerrarCliente: () => set({ clienteAbiertoId: null }),
  reset: () => set({ clienteAbiertoId: null }),
}));
