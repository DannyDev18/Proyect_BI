import { create } from 'zustand';
import type { ClienteBusqueda } from '../types/crossSelling';

export interface CanastaItem {
  codart: string;
  nombre: string;
}

interface CrossSellStore {
  cliente: ClienteBusqueda | null;
  setCliente: (cliente: ClienteBusqueda | null) => void;
  canasta: CanastaItem[];
  agregarACanasta: (item: CanastaItem) => void;
  quitarDeCanasta: (codart: string) => void;
  /** Auditoría 43 (H43-9): invocado desde el cierre de sesión -- sin `persist`, el
   * cliente (PII) igual sobrevivía en memoria entre logins porque el store nunca se
   * recrea con una navegación SPA. */
  reset: () => void;
}

/** Fase 1 de docs/features/plan_refactor_venta_cruzada_ia.md (CAMBIO 1): el cliente
 * es el estado raíz de la página de Venta Cruzada, compartido entre paneles hermanos
 * no anidados (perfil, asistente de canasta, simulación de la Fase 3, combos de la
 * Fase 4) -- de ahí Zustand en vez de useState local. `canasta` se mueve aquí en la
 * Fase 3 (§3 punto 2 del plan: "la canasta en Zustand dispara una query con
 * useDebouncedValue"), antes vivía en `SaleAssistant.tsx`. Sin `persist`: `cliente`
 * trae PII real (nombre) y no debe sobrevivir en sessionStorage entre sesiones. */
export const useCrossSellStore = create<CrossSellStore>((set) => ({
  cliente: null,
  setCliente: (cliente) => set({ cliente }),
  canasta: [],
  agregarACanasta: (item) => set((s) => (s.canasta.some((c) => c.codart === item.codart) ? s : { canasta: [...s.canasta, item] })),
  quitarDeCanasta: (codart) => set((s) => ({ canasta: s.canasta.filter((c) => c.codart !== codart) })),
  reset: () => set({ cliente: null, canasta: [] }),
}));
