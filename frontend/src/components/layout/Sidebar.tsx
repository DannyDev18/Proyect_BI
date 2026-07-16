import { NavLink, useLocation } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';
import {
  PackageSearch,
  TrendingUp,
  ShieldAlert,
  LayoutDashboard,
  Users,
  Target,
  Sparkles,
  ChevronDown,
  ChevronsLeft,
  ChevronsRight,
} from 'lucide-react';
import { useAuthStore } from '../../store/authStore';
import { useUIStore } from '../../store/uiStore';
import { getNavItemsForRole, getSubNavItemsForRole, type RouteKey } from '../../constants/permissions';
import { Collapse } from '../ui/Collapse';
import { Tooltip } from '../ui/Tooltip';
import { Dropdown } from '../ui/Dropdown';
import { UserMenuContent, initials, roleLabel } from './UserMenu';

// Icons are a presentation concern, kept local to the Sidebar rather than in the permissions map.
const NAV_ICONS: Partial<Record<RouteKey, ReactNode>> = {
  admin: <ShieldAlert size={20} />,
  users: <Users size={20} />,
  gerencia: <LayoutDashboard size={20} />,
  bodega: <PackageSearch size={20} />,
  ventas: <TrendingUp size={20} />,
};
const SUB_NAV_ICONS: Partial<Record<RouteKey, ReactNode>> = {
  'gerencia.metas': <Target size={16} />,
  'ventas.metas': <Target size={16} />,
  'ventas.cross-selling': <Sparkles size={16} />,
};

export const Sidebar = () => {
  const { user } = useAuthStore();
  const { isSidebarOpen, closeSidebar, isSidebarCollapsed, toggleSidebarCollapsed } = useUIStore();
  const location = useLocation();
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});

  const role = user?.role;
  const allowedItems = role
    ? getNavItemsForRole(role).map((item) => ({
        ...item,
        icon: NAV_ICONS[item.routeKey],
        subItems: getSubNavItemsForRole(role, item.routeKey).map((sub) => ({
          ...sub,
          icon: SUB_NAV_ICONS[sub.routeKey],
        })),
      }))
    : [];

  // El grupo de la ruta activa se abre solo (F3, D-4).
  useEffect(() => {
    const active = allowedItems.find((item) => location.pathname.startsWith(item.path));
    if (active && active.subItems.length > 0) {
      setOpenGroups((prev) => (prev[active.routeKey] ? prev : { ...prev, [active.routeKey]: true }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  if (!user) return null;

  const collapsed = isSidebarCollapsed;

  return (
    <aside
      className={`fixed md:relative h-full border-r border-border bg-bg-sidebar flex flex-col z-40 transition-all duration-slow ease-in-out
        ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}
        ${collapsed ? 'w-64 md:w-[76px]' : 'w-64'}
      `}
    >
      {/* Toggle colapsado — solo desktop */}
      <button
        type="button"
        onClick={toggleSidebarCollapsed}
        aria-label={collapsed ? 'Expandir menú' : 'Colapsar menú'}
        className="hidden md:flex absolute -right-3 top-7 w-6 h-6 items-center justify-center rounded-full
          bg-bg-elevated border border-border text-slate-400 hover:text-primary hover:border-primary/40
          transition-colors duration-fast cursor-pointer focus-ring z-10"
      >
        {collapsed ? <ChevronsRight size={13} /> : <ChevronsLeft size={13} />}
      </button>

      {/* Marca */}
      <div className="h-16 flex items-center px-6 border-b border-border flex-shrink-0 overflow-hidden">
        <span className="relative flex-shrink-0 w-2 h-2 rounded-full bg-gradient-to-br from-primary to-accent">
          <span className="absolute inset-0 rounded-full bg-primary animate-pulse-slow" />
        </span>
        {!collapsed && (
          <span className="ml-3 font-display font-semibold tracking-tight text-text-primary text-lg whitespace-nowrap">
            Signal Deck
          </span>
        )}
      </div>

      <div className="p-3 flex-1 overflow-y-auto overflow-x-hidden w-full">
        {!collapsed && (
          <div className="text-xs uppercase tracking-wider text-slate-500 font-semibold mb-3 px-3">Dashboards</div>
        )}
        <nav className="space-y-1">
          {allowedItems.map((item) => {
            const hasSub = item.subItems.length > 0;
            const groupOpen = !!openGroups[item.routeKey];
            const navLink = (
              <NavLink
                onClick={!hasSub ? closeSidebar : undefined}
                end={!hasSub}
                to={item.path}
                className={({ isActive }) =>
                  `group relative flex items-center px-3 py-2.5 rounded-lg transition-all duration-fast text-sm font-medium focus-ring ${
                    isActive
                      ? 'bg-primary/10 text-primary border border-primary/20'
                      : 'text-slate-400 hover:bg-bg-hover hover:text-slate-200 border border-transparent'
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    {isActive && (
                      <span className="absolute left-0 top-1.5 bottom-1.5 w-0.5 rounded-full bg-primary glow-accent-sm animate-fade-in" />
                    )}
                    <span className={collapsed ? '' : 'mr-3'}>{item.icon}</span>
                    {!collapsed && <span className="flex-1">{item.label}</span>}
                  </>
                )}
              </NavLink>
            );

            return (
              <div key={item.routeKey}>
                <div className="flex items-center gap-0.5">
                  {collapsed ? (
                    <Tooltip label={item.label} side="right" className="w-full">
                      {navLink}
                    </Tooltip>
                  ) : (
                    <div className="flex-1">{navLink}</div>
                  )}
                  {hasSub && !collapsed && (
                    <button
                      type="button"
                      onClick={() => setOpenGroups((prev) => ({ ...prev, [item.routeKey]: !groupOpen }))}
                      aria-label={groupOpen ? `Colapsar ${item.label}` : `Expandir ${item.label}`}
                      aria-expanded={groupOpen}
                      className="p-1.5 rounded-md text-slate-500 hover:text-slate-200 hover:bg-bg-hover transition-colors duration-fast cursor-pointer focus-ring"
                    >
                      <ChevronDown size={14} className={`transition-transform duration-fast ${groupOpen ? 'rotate-180' : ''}`} />
                    </button>
                  )}
                </div>
                {hasSub && !collapsed && (
                  <Collapse open={groupOpen}>
                    <div className="ml-6 mt-1 space-y-1 border-l border-border pl-2 pb-1">
                      {item.subItems.map((sub) => (
                        <NavLink
                          onClick={closeSidebar}
                          key={sub.routeKey}
                          to={sub.path}
                          className={({ isActive }) =>
                            `flex items-center px-3 py-2 rounded-lg transition-colors duration-fast text-xs font-medium focus-ring ${
                              isActive
                                ? 'text-primary bg-primary/10 border border-primary/20'
                                : 'text-slate-500 hover:text-slate-300 hover:bg-bg-hover'
                            }`
                          }
                        >
                          <span className="mr-2">{sub.icon}</span>
                          {sub.label}
                        </NavLink>
                      ))}
                    </div>
                  </Collapse>
                )}
              </div>
            );
          })}
        </nav>
      </div>

      {/* Bloque de perfil (F3.5b) — patrón Linear/Supabase: el perfil vive aquí y en el
          Header porque el sidebar colapsado oculta este bloque. */}
      <div className="p-3 border-t border-border flex-shrink-0 w-full">
        <Dropdown
          placement="top"
          align={collapsed ? 'start' : 'end'}
          className="w-full"
          trigger={({ toggle }) =>
            collapsed ? (
              <Tooltip label={`${user.name} · ${roleLabel(user.role)}`} side="right" className="w-full">
                <button
                  type="button"
                  onClick={toggle}
                  aria-label="Menú de usuario"
                  className="w-full flex items-center justify-center py-1.5 rounded-lg hover:bg-bg-hover transition-colors duration-fast cursor-pointer focus-ring"
                >
                  <span className="w-9 h-9 rounded-full bg-bg-elevated border border-border flex items-center justify-center text-xs font-semibold text-primary">
                    {initials(user.name)}
                  </span>
                </button>
              </Tooltip>
            ) : (
              <button
                type="button"
                onClick={toggle}
                className="w-full flex items-center gap-2.5 px-2 py-2 rounded-lg hover:bg-bg-hover transition-colors duration-fast cursor-pointer focus-ring text-left"
              >
                <span className="relative flex-shrink-0 w-9 h-9 rounded-full bg-bg-elevated border border-border flex items-center justify-center text-xs font-semibold text-primary">
                  {initials(user.name)}
                  <span className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-success border-2 border-bg-sidebar" title="Sesión activa" />
                </span>
                <span className="flex-1 min-w-0">
                  <span className="block text-sm font-medium text-slate-200 truncate">{user.name}</span>
                  <span className="block text-xs text-slate-500 truncate">
                    {roleLabel(user.role)}{user.sucursalId ? ` · Suc. ${user.sucursalId}` : ''}
                  </span>
                </span>
              </button>
            )
          }
        >
          <UserMenuContent />
        </Dropdown>
      </div>
    </aside>
  );
};
