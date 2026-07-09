import { NavLink } from 'react-router-dom';
import type { ReactNode } from 'react';
import {
  Building2,
  PackageSearch,
  TrendingUp,
  ShieldAlert,
  Settings,
  LayoutDashboard,
  Users,
  Target
} from 'lucide-react';
import { useAuthStore } from '../../store/authStore';
import { useUIStore } from '../../store/uiStore';
import { getNavItemsForRole, getSubNavItemsForRole, type RouteKey } from '../../constants/permissions';

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
};

export const Sidebar = () => {
  const { user } = useAuthStore();
  const { isSidebarOpen, closeSidebar } = useUIStore();

  if (!user) return null;

  const role = user.role;
  const allowedItems = getNavItemsForRole(role).map((item) => ({
    ...item,
    icon: NAV_ICONS[item.routeKey],
    subItems: getSubNavItemsForRole(role, item.routeKey).map((sub) => ({
      ...sub,
      icon: SUB_NAV_ICONS[sub.routeKey],
    })),
  }));

  return (
    <aside
      className={`fixed md:relative w-64 h-full border-r border-slate-800 bg-slate-950 flex flex-col z-40 transition-transform duration-300 ease-in-out
        ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}
      `}
    >
      <div className="h-16 flex items-center px-6 border-b border-slate-800 flex-shrink-0">
        <Building2 className="text-blue-500 mr-3" />
        <span className="font-sans font-semibold tracking-tight text-slate-100 text-lg">BI Platform</span>
      </div>
      
      <div className="p-4 flex-1 overflow-y-auto w-full">
        <div className="text-xs uppercase tracking-wider text-slate-500 font-semibold mb-4 px-2">Dashboards</div>
        <nav className="space-y-1">
          {allowedItems.map((item) => (
            <div key={item.routeKey}>
              <NavLink
                onClick={item.subItems.length === 0 ? closeSidebar : undefined}
                end={item.subItems.length === 0}
                to={item.path}
                className={({ isActive }) =>
                  `flex items-center px-3 py-2.5 rounded-lg transition-all duration-200 text-sm font-medium ${
                    isActive
                      ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                      : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200 border border-transparent'
                  }`
                }
              >
                <span className="mr-3">{item.icon}</span>
                {item.label}
              </NavLink>
              {item.subItems.length > 0 && (
                <div className="ml-6 mt-1 space-y-1 border-l border-slate-800 pl-2">
                  {item.subItems.map(sub => (
                    <NavLink
                      onClick={closeSidebar}
                      key={sub.routeKey}
                      to={sub.path}
                      className={({ isActive }) =>
                        `flex items-center px-3 py-2 rounded-lg transition-all duration-200 text-xs font-medium ${
                          isActive
                            ? 'text-teal-400 bg-teal-500/10 border border-teal-500/20'
                            : 'text-slate-500 hover:text-slate-300 hover:bg-slate-800/50'
                        }`
                      }
                    >
                      <span className="mr-2">{sub.icon}</span>
                      {sub.label}
                    </NavLink>
                  ))}
                </div>
              )}
            </div>
          ))}
        </nav>
      </div>

      <div className="p-4 border-t border-slate-800 flex-shrink-0 w-full">
        <NavLink 
          onClick={closeSidebar}
          to="/settings" 
          className={({ isActive }) =>
            `flex items-center px-3 py-2.5 rounded-lg transition-all duration-200 text-sm font-medium ${
              isActive 
                ? 'bg-slate-800/80 text-slate-200 border border-slate-700' 
                : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200 border border-transparent'
            }`
          }
        >
          <Settings size={20} className="mr-3" />
          General Settings
        </NavLink>
      </div>
    </aside>
  );
};
