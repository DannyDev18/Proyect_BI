import type { Role } from '../types/auth';

export interface RouteConfig {
  path: string;
  /** undefined = any authenticated role may access */
  allowedRoles: Role[] | undefined;
  nav?: { label: string };
}

export type RouteKey = 'admin' | 'admin.usuarios' | 'gerencia' | 'gerencia.metas' | 'bodega' | 'bodega.almacenes' | 'bodega.reportes' | 'bodega.reabastecimiento' | 'ventas' | 'ventas.metas' | 'ventas.cross-selling' | 'ventas.cartera360' | 'ventas.ruta' | 'settings';
// Nota: 'bodega.compras' (Compras y Proveedores) y 'gerencia.cartera' (Cartera y Flujo de
// Caja) se retiraron del alcance -- ver docs/auditoria/31_.../33_... para el análisis de
// datos que motivó su implementación original y esta decisión de descope.

export const ROUTES: Record<RouteKey, RouteConfig> = {
  admin: {
    path: '/admin',
    allowedRoles: ['administrador'],
    nav: { label: 'Sistema & Logs' },
  },
  // Fase 5 §5.4 (docs/features/plan_correcciones_integrales_sistema.md): anidado bajo
  // /admin/usuarios (antes ruta hermana /users, sin relación jerárquica visible).
  'admin.usuarios': {
    path: '/admin/usuarios',
    allowedRoles: ['administrador'],
    nav: { label: 'Gestión de Usuarios' },
  },
  gerencia: {
    path: '/gerencia',
    allowedRoles: ['administrador', 'gerencia'],
    nav: { label: 'Visión Ejecutiva' },
  },
  'gerencia.metas': {
    path: '/gerencia/metas',
    allowedRoles: ['administrador', 'gerencia'],
    nav: { label: 'Metas y Comisiones' },
  },
  bodega: {
    path: '/bodega',
    allowedRoles: ['administrador', 'gerencia', 'bodega'],
    nav: { label: 'Control de Inventario' },
  },
  'bodega.almacenes': {
    path: '/bodega/almacenes',
    allowedRoles: ['administrador', 'gerencia', 'bodega'],
    nav: { label: 'Status por Almacén' },
  },
  'bodega.reportes': {
    path: '/bodega/reportes',
    allowedRoles: ['administrador', 'gerencia', 'bodega'],
    nav: { label: 'Reportes de Abastecimiento' },
  },
  // Reabastecimiento Inteligente (docs/features/plan_reabastecimiento_inteligente.md,
  // F0-F4 de esta sesión): sistema de apoyo a decisiones de compra por riesgo real de
  // quiebre (stock de seguridad + punto de reorden), convive con `bodega.almacenes`.
  'bodega.reabastecimiento': {
    path: '/bodega/reabastecimiento',
    allowedRoles: ['administrador', 'gerencia', 'bodega'],
    nav: { label: 'Reabastecimiento Inteligente' },
  },
  // Petición explícita del usuario: gerencia deja de ver las páginas de Ventas que
  // reflejan la operación PERSONAL de un vendedor (Gestión Comercial y sus 4 sub-páginas
  // -- Mi Meta y Comisión, Venta Cruzada, Mi Ruta Inteligente, y el escape hatch
  // Cartera 360) -- gerencia sigue teniendo su propia consola de Metas y Comisiones
  // (`gerencia.metas`, la vista oficial de aprobación/configuración, no la personal del
  // vendedor) sin cambios.
  ventas: {
    path: '/ventas',
    allowedRoles: ['administrador', 'ventas'],
    nav: { label: 'Gestión Comercial' },
  },
  'ventas.metas': {
    path: '/ventas/metas',
    allowedRoles: ['administrador', 'ventas'],
    nav: { label: 'Mi Meta y Comisión' },
  },
  'ventas.cross-selling': {
    path: '/ventas/cross-selling',
    allowedRoles: ['administrador', 'ventas'],
    nav: { label: 'Venta Cruzada' },
  },
  // "Mi Ruta Inteligente de Ventas" (docs/features/plan_refactor_cartera360_ruta_
  // inteligente.md §7 Estrategia de migración): "el Sidebar apunta a la nueva desde la
  // Fase 3; la vieja queda accesible por URL directa como escape hatch" -- por eso
  // 'ventas.cartera360' pierde su `nav` (sigue registrada, sigue funcionando, solo deja
  // de aparecer en el menú) y 'ventas.ruta' lo gana. Requiere
  // CARTERA360_RUTA_INTELIGENTE_ENABLED=true en el backend (si está en false, esta
  // página carga pero sus llamadas a /ruta/* devuelven 404).
  'ventas.cartera360': {
    path: '/ventas/cartera360',
    allowedRoles: ['administrador', 'ventas'],
  },
  'ventas.ruta': {
    path: '/ventas/ruta',
    allowedRoles: ['administrador', 'ventas'],
    nav: { label: 'Mi Ruta Inteligente' },
  },
  settings: {
    path: '/settings',
    allowedRoles: undefined,
  },
};

export const canAccess = (role: Role, routeKey: RouteKey): boolean => {
  const allowedRoles = ROUTES[routeKey].allowedRoles;
  return !allowedRoles || allowedRoles.includes(role);
};

export interface NavItem {
  routeKey: RouteKey;
  path: string;
  label: string;
}

/** Top-level nav items (no dot in the key) allowed for a role, in ROUTES declaration order. */
export const getNavItemsForRole = (role: Role): NavItem[] =>
  (Object.keys(ROUTES) as RouteKey[])
    .filter((key) => !key.includes('.'))
    .filter((key) => ROUTES[key].nav && canAccess(role, key))
    .map((key) => ({ routeKey: key, path: ROUTES[key].path, label: ROUTES[key].nav!.label }));

/** Sub-nav items (dotted key, e.g. 'gerencia.metas') nested under a given parent key. */
export const getSubNavItemsForRole = (role: Role, parentKey: RouteKey): NavItem[] =>
  (Object.keys(ROUTES) as RouteKey[])
    .filter((key) => key.startsWith(`${parentKey}.`))
    .filter((key) => ROUTES[key].nav && canAccess(role, key))
    .map((key) => ({ routeKey: key, path: ROUTES[key].path, label: ROUTES[key].nav!.label }));

/** Breadcrumb derivado de la jerarquía real de rutas (F3, D-5): cero fuente de verdad
 * nueva, los labels ya existen en ROUTES. Devuelve [padre?, ruta actual] cuando la ruta
 * activa tiene un dot en su key (p. ej. 'ventas.cross-selling' -> Gestión Comercial › Venta Cruzada). */
export const getBreadcrumbForPath = (pathname: string): { label: string; path: string }[] => {
  const entries = Object.entries(ROUTES) as [RouteKey, RouteConfig][];
  const match = entries.find(([, cfg]) => cfg.path === pathname) ?? entries.find(([, cfg]) => pathname.startsWith(`${cfg.path}/`));
  if (!match || !match[1].nav) return [];
  const [key, cfg] = match;
  const trail: { label: string; path: string }[] = [{ label: cfg.nav!.label, path: cfg.path }];
  if (key.includes('.')) {
    const parentKey = key.split('.')[0] as RouteKey;
    const parent = ROUTES[parentKey];
    if (parent?.nav) trail.unshift({ label: parent.nav.label, path: parent.path });
  }
  return trail;
};
