import { LogOut, User as UserIcon, Bell, Menu } from 'lucide-react';
import { useAuthStore } from '../../store/authStore';
import { useUIStore } from '../../store/uiStore';
import { useNavigate } from 'react-router-dom';
import { canAccess } from '../../constants/permissions';
import { NotificationBell } from '../bodega/NotificationBell';

export const Header = () => {
  const { user, logout } = useAuthStore();
  const { toggleSidebar } = useUIStore();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <header className="h-16 border-b border-slate-800 bg-slate-950 px-4 md:px-6 flex items-center justify-between sticky top-0 z-20">
      <div className="flex items-center">
        <button
          onClick={toggleSidebar}
          aria-label="Alternar menú de navegación"
          className="md:hidden mr-4 p-2 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-lg transition-colors cursor-pointer focus-ring"
        >
          <Menu size={24} />
        </button>

        {user?.sucursalId && (
          <span className="hidden sm:inline-block text-sm font-medium px-3 py-1 bg-slate-800 text-slate-300 rounded-full border border-slate-700">
            Sucursal: {user.sucursalId}
          </span>
        )}
      </div>

      <div className="flex items-center space-x-4 md:space-x-6">
        {user && canAccess(user.role, 'bodega') ? (
          <NotificationBell />
        ) : (
          <button
            disabled
            aria-label="Notificaciones (próximamente)"
            title="Notificaciones — próximamente"
            className="text-slate-600 cursor-not-allowed"
          >
            <Bell size={20} />
          </button>
        )}

        <div className="h-8 w-px bg-slate-800"></div>

        <div className="flex items-center space-x-3">
          <div className="text-right hidden sm:block">
            <div className="text-sm font-medium text-slate-200">{user?.name}</div>
            <div className="text-xs text-slate-500 font-mono">{user?.role}</div>
          </div>
          <div className="w-9 h-9 rounded-full bg-slate-800 flex items-center justify-center border border-slate-700 text-slate-300">
            <UserIcon size={18} />
          </div>
        </div>
        
        <button
          onClick={handleLogout}
          aria-label="Cerrar sesión"
          className="ml-2 sm:ml-4 p-2 text-slate-400 hover:text-red-400 hover:bg-red-400/10 rounded-lg transition-all cursor-pointer focus-ring"
          title="Logout"
        >
          <LogOut size={20} />
        </button>
      </div>
    </header>
  );
};
