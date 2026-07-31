// frontend/src/services/session.ts
/**
 * Punto único de cierre de sesión (auditoría 43, H43-8..H43-12,
 * docs/auditoria/43_correcciones_sesion_ventas_y_datos.md).
 *
 * Antes, `UserMenuContent` llamaba a `useAuthStore.logout()` directamente, y el
 * interceptor 401 de `http.ts` duplicaba a mano el borrado de `localStorage`. Ninguno de
 * los dos limpiaba: la caché de TanStack Query (singleton que sobrevive a la navegación
 * SPA sin recarga), los stores Zustand con estado sensible (`crossSellStore`,
 * `rutaVentasStore`), ni `sessionStorage` (filtros de Bodega). Resultado: al loguearse un
 * usuario B en la misma pestaña, veía paneles con datos cacheados del usuario A hasta que
 * el primer refetch de cada query terminara -- el síntoma exacto reportado.
 *
 * `cerrarSesion()` es el único punto que debe invocarse para salir de la aplicación;
 * `useAuthStore.logout()` NUNCA debe llamarse directamente fuera de aquí.
 */
import { api } from './http';
import { queryClient } from '../app/providers';
import { useAuthStore } from '../store/authStore';
import { useCrossSellStore } from '../store/crossSellStore';
import { useRutaVentasStore } from '../store/rutaVentasStore';
import { useBodegaFiltersStore } from '../store/bodegaFiltersStore';

/** Limpieza local (caché de queries, stores sensibles, sessionStorage, localStorage de
 * auth) -- sin llamar al backend. Usado tanto por `cerrarSesion()` (logout explícito)
 * como por el interceptor 401 de `http.ts` (el token ya no sirve; no tiene sentido
 * pedirle al backend que revoque un token que la propia API acaba de rechazar). */
export const limpiarSesionLocal = (): void => {
  queryClient.clear();

  useCrossSellStore.getState().reset();
  useRutaVentasStore.getState().reset();
  useBodegaFiltersStore.getState().reset();

  // `reset()` de bodegaFiltersStore ya reescribe sessionStorage vía el middleware
  // `persist`, pero se limpia también a nivel de storage completo como defensa en
  // profundidad ante cualquier clave de sesión futura que se agregue sin pasar por un
  // store con `reset()` propio.
  sessionStorage.clear();

  useAuthStore.getState().logout();
};

/** Cierre de sesión explícito (botón "Cerrar sesión"): revoca el token del lado del
 * servidor (H43-12) y luego hace la misma limpieza local que el interceptor 401. */
export const cerrarSesion = async (): Promise<void> => {
  // Best-effort: si falla (red caída, token ya expirado), igual se completa el cierre
  // local -- el usuario no debe quedar atrapado en la sesión por un error de red al salir.
  try {
    await api.post('/auth/logout');
  } catch {
    // intencional: ver comentario arriba
  }

  limpiarSesionLocal();
};
