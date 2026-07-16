import { ChevronRight, Menu } from 'lucide-react';
import { useAuthStore } from '../../store/authStore';
import { useUIStore } from '../../store/uiStore';
import { useLocation, Link } from 'react-router-dom';
import { NotificationBell } from './NotificationBell';
import { Dropdown } from '../ui/Dropdown';
import { Badge } from '../ui/Badge';
import { UserMenuContent, initials, roleLabel } from './UserMenu';
import { getBreadcrumbForPath } from '../../constants/permissions';

export const Header = () => {
  const { user } = useAuthStore();
  const { toggleSidebar } = useUIStore();
  const location = useLocation();
  const breadcrumb = getBreadcrumbForPath(location.pathname);

  return (
    <header className="h-16 border-b border-border bg-bg-surface px-4 md:px-6 flex items-center justify-between sticky top-0 z-20">
      <div className="flex items-center min-w-0">
        <button
          onClick={toggleSidebar}
          aria-label="Alternar menú de navegación"
          className="md:hidden mr-4 p-2 text-slate-400 hover:text-slate-200 hover:bg-bg-hover rounded-lg transition-colors cursor-pointer focus-ring"
        >
          <Menu size={24} />
        </button>

        {/* Breadcrumb derivado de la jerarquía real de rutas (F3, D-5) */}
        <nav aria-label="Ruta de navegación" className="flex items-center gap-1.5 text-sm min-w-0 truncate">
          {breadcrumb.map((crumb, i) => (
            <span key={crumb.path} className="flex items-center gap-1.5 min-w-0">
              {i > 0 && <ChevronRight size={14} className="text-slate-600 flex-shrink-0" />}
              {i === breadcrumb.length - 1 ? (
                <span className="font-medium text-slate-200 truncate">{crumb.label}</span>
              ) : (
                <Link to={crumb.path} className="text-slate-500 hover:text-slate-300 transition-colors truncate focus-ring rounded">
                  {crumb.label}
                </Link>
              )}
            </span>
          ))}
        </nav>

        {user?.sucursalId && (
          <Badge variant="neutral" className="hidden sm:inline-flex ml-4 flex-shrink-0">
            Sucursal: {user.sucursalId}
          </Badge>
        )}
      </div>

      <div className="flex items-center space-x-3 md:space-x-4 flex-shrink-0">
        {user && <NotificationBell />}

        <div className="h-8 w-px bg-border" />

        {user && (
          <Dropdown
            align="end"
            trigger={({ toggle }) => (
              <button
                type="button"
                onClick={toggle}
                aria-label="Menú de usuario"
                className="flex items-center gap-2.5 pl-1 pr-2 py-1 rounded-lg hover:bg-bg-hover transition-colors duration-fast cursor-pointer focus-ring"
              >
                <span className="w-8 h-8 rounded-full bg-bg-elevated border border-border flex items-center justify-center text-xs font-semibold text-primary flex-shrink-0">
                  {initials(user.name)}
                </span>
                <span className="text-right hidden sm:block">
                  <span className="block text-sm font-medium text-slate-200 leading-tight">{user.name}</span>
                  <span className="block text-xs text-slate-500 font-mono leading-tight">{roleLabel(user.role)}</span>
                </span>
              </button>
            )}
          >
            <UserMenuContent />
          </Dropdown>
        )}
      </div>
    </header>
  );
};
