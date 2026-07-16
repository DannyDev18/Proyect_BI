import { create } from 'zustand';

const SIDEBAR_COLLAPSED_KEY = 'ui_sidebar_collapsed';

interface UIState {
  isSidebarOpen: boolean;
  toggleSidebar: () => void;
  closeSidebar: () => void;
  isSidebarCollapsed: boolean;
  toggleSidebarCollapsed: () => void;
}

export const useUIStore = create<UIState>((set) => ({
  isSidebarOpen: false,
  toggleSidebar: () => set((state) => ({ isSidebarOpen: !state.isSidebarOpen })),
  closeSidebar: () => set({ isSidebarOpen: false }),

  // Modo colapsado a solo-iconos en desktop (F3, D-4): estado UI puro persistido en
  // localStorage, no un dato de negocio -- permitido por invariante 1 del plan.
  isSidebarCollapsed: localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true',
  toggleSidebarCollapsed: () => set((state) => {
    const next = !state.isSidebarCollapsed;
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(next));
    return { isSidebarCollapsed: next };
  }),
}));
