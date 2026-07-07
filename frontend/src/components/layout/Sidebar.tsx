import { NavLink } from 'react-router-dom';
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

export const Sidebar = () => {
  const { user } = useAuthStore();
  const { isSidebarOpen, closeSidebar } = useUIStore();
  
  if (!user) return null;

  const role = user.role;

  const navItems = [
    {
      to: '/admin',
      icon: <ShieldAlert size={20} />,
      label: 'Sistema & Logs',
      roles: ['administrador']
    },
    {
      to: '/users',
      icon: <Users size={20} />,
      label: 'Gestión de Usuarios',
      roles: ['administrador']
    },
    {
      to: '/gerencia',
      icon: <LayoutDashboard size={20} />,
      label: 'Visión Ejecutiva',
      roles: ['administrador', 'gerencia'],
      subItems: [
        {
          to: '/gerencia/metas',
          icon: <Target size={16} />,
          label: 'Metas y Comisiones',
          roles: ['administrador', 'gerencia']
        }
      ]
    },
    {
      to: '/bodega',
      icon: <PackageSearch size={20} />,
      label: 'Control de Inventario',
      roles: ['administrador', 'gerencia', 'bodega']
    },
    {
      to: '/ventas',
      icon: <TrendingUp size={20} />,
      label: 'Gestión Comercial',
      roles: ['administrador', 'gerencia', 'ventas']
    }
  ];

  const allowedItems = navItems.filter(item => item.roles.includes(role));

  return (
    <aside 
      className={`fixed md:relative w-64 h-full border-r border-slate-800 bg-slate-950/90 md:bg-slate-950/50 backdrop-blur-xl flex flex-col z-40 transition-transform duration-300 ease-in-out
        ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}
      `}
    >
      <div className="h-16 flex items-center px-6 border-b border-slate-800 flex-shrink-0">
        <Building2 className="text-blue-500 mr-3" />
        <span className="font-display font-semibold tracking-tight text-slate-100 text-lg">BI Platform</span>
      </div>
      
      <div className="p-4 flex-1 overflow-y-auto w-full">
        <div className="text-xs uppercase tracking-wider text-slate-500 font-semibold mb-4 px-2">Dashboards</div>
        <nav className="space-y-1">
          {allowedItems.map((item) => (
            <div key={item.to}>
              <NavLink
                onClick={!item.subItems ? closeSidebar : undefined}
                end={!item.subItems}
                to={item.to}
                className={({ isActive }) =>
                  `flex items-center px-3 py-2.5 rounded-lg transition-all duration-200 text-sm font-medium ${
                    isActive 
                      ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20 shadow-[0_0_15px_rgba(59,130,246,0.1)]' 
                      : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200 border border-transparent'
                  }`
                }
              >
                <span className="mr-3">{item.icon}</span>
                {item.label}
              </NavLink>
              {item.subItems && (
                <div className="ml-6 mt-1 space-y-1 border-l border-slate-800 pl-2">
                  {item.subItems.filter(s => s.roles.includes(role)).map(sub => (
                    <NavLink
                      onClick={closeSidebar}
                      key={sub.to}
                      to={sub.to}
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
