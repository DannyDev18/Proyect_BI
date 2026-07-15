import type { Role } from '../types/auth';

export interface RouteConfig {
  path: string;
  /** undefined = any authenticated role may access */
  allowedRoles: Role[] | undefined;
  nav?: { label: string };
}

export type RouteKey = 'admin' | 'users' | 'gerencia' | 'gerencia.metas' | 'bodega' | 'bodega.almacenes' | 'bodega.reportes' | 'ventas' | 'ventas.metas' | 'ventas.cross-selling' | 'ventas.cartera360' | 'settings';
// Nota: 'bodega.compras' (Compras y Proveedores) y 'gerencia.cartera' (Cartera y Flujo de
// Caja) se retiraron del alcance -- ver docs/auditoria/31_.../33_... para el análisis de
// datos que motivó su implementación original y esta decisión de descope.

export const ROUTES: Record<RouteKey, RouteConfig> = {
  admin: {
    path: '/admin',
    allowedRoles: ['administrador'],
    nav: { label: 'Sistema & Logs' },
  },
  users: {
    path: '/users',
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
  ventas: {
    path: '/ventas',
    allowedRoles: ['administrador', 'gerencia', 'ventas'],
    nav: { label: 'Gestión Comercial' },
  },
  'ventas.metas': {
    path: '/ventas/metas',
    allowedRoles: ['administrador', 'gerencia', 'ventas'],
    nav: { label: 'Mi Meta y Comisión' },
  },
  'ventas.cross-selling': {
    path: '/ventas/cross-selling',
    allowedRoles: ['administrador', 'gerencia', 'ventas'],
    nav: { label: 'Venta Cruzada' },
  },
  'ventas.cartera360': {
    path: '/ventas/cartera360',
    allowedRoles: ['administrador', 'gerencia', 'ventas'],
    nav: { label: 'Cartera 360' },
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
