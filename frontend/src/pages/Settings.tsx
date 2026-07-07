import { Settings as SettingsIcon, Shield, Bell, Palette } from 'lucide-react';
import { useAuthStore } from '../store/authStore';

export const Settings = () => {
  const { user } = useAuthStore();
  
  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-3xl font-display font-semibold">Configuración General</h1>
          <p className="text-slate-400 mt-1">Ajustes de cuenta y preferencias del sistema</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <div className="col-span-1 border-r border-slate-800 pr-4 space-y-2">
          <button className="w-full text-left px-4 py-2 rounded-lg bg-blue-500/10 text-blue-400 border border-blue-500/20 font-medium flex items-center shadow-[0_0_15px_rgba(59,130,246,0.1)]">
            <Shield size={18} className="mr-3" /> Perfil
          </button>
          <button className="w-full text-left px-4 py-2 rounded-lg hover:bg-slate-800/50 text-slate-400 hover:text-slate-200 transition-colors flex items-center">
            <Bell size={18} className="mr-3" /> Notificaciones
          </button>
          <button className="w-full text-left px-4 py-2 rounded-lg hover:bg-slate-800/50 text-slate-400 hover:text-slate-200 transition-colors flex items-center">
            <Palette size={18} className="mr-3" /> Apariencia
          </button>
        </div>

        <div className="col-span-3 bg-slate-900/50 backdrop-blur-sm border border-slate-800 rounded-xl p-6 shadow-lg">
          <h3 className="text-lg font-display font-semibold text-slate-200 mb-6 flex items-center border-b border-slate-800 pb-4">
            <SettingsIcon className="mr-3 text-slate-400" /> Detalles de la Cuenta
          </h3>
          
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">Nombre Completo</label>
              <input 
                type="text" 
                disabled 
                value={user?.name || ''} 
                className="w-full px-4 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-400 focus:outline-none cursor-not-allowed"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">Correo Electrónico</label>
              <input 
                type="email" 
                disabled 
                value={user?.email || ''} 
                className="w-full px-4 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-400 focus:outline-none cursor-not-allowed"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">Rol Asignado</label>
              <input 
                type="text" 
                disabled 
                value={(user?.role || '').toUpperCase()} 
                className="w-full px-4 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-400 focus:outline-none cursor-not-allowed font-mono"
              />
            </div>
          </div>
          
          <div className="mt-8 flex justify-end">
             <button className="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg shadow-[0_0_15px_rgba(59,130,246,0.2)] transition text-sm font-medium">
               Guardar Cambios
             </button>
          </div>
        </div>
      </div>
    </div>
  );
};
