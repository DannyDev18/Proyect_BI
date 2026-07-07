import { Link } from 'react-router-dom';
import { ShieldAlert } from 'lucide-react';

export const AccessDenied = () => {
  return (
    <div className="flex flex-col items-center justify-center h-full min-h-[60vh]">
      <div className="w-24 h-24 rounded-full bg-red-500/10 border border-red-500/20 flex items-center justify-center mb-6 shadow-[0_0_30px_rgba(239,68,68,0.15)]">
        <ShieldAlert size={48} className="text-red-500" />
      </div>
      <h1 className="text-3xl font-display font-bold text-slate-100 mb-3">Acceso Denegado</h1>
      <p className="text-slate-400 max-w-md text-center mb-8">
        No tienes los privilegios necesarios para ver esta información. El intento de acceso ha sido registrado en los logs de seguridad.
      </p>
      
      <Link 
        to="/" 
        className="px-6 py-3 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-lg transition-colors"
      >
        Volver al Inicio
      </Link>
    </div>
  );
};
