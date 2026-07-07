import { useState } from 'react';
import { useAuthStore } from '../../store/authStore';

export const GlobalBranchSelector = ({ onSelectSucursal }: { onSelectSucursal: (sucursalId: string | null) => void }) => {
  const { user } = useAuthStore();
  const [selected, setSelected] = useState<string>('ALL');

  // Solo Gerentes y Administradores pueden ver el selector global
  const isGlobalRole = user?.role === 'gerencia' || user?.role === 'administrador';
  if (!isGlobalRole) return null;

  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    setSelected(val);
    // Al seleccionar "ALL" (nulo), la API asume búsqueda de consolidación global.
    onSelectSucursal(val === 'ALL' ? null : val);
  };

  return (
    <div className="flex items-center space-x-2 animate-fade-in bg-slate-900/50 p-1.5 rounded-lg border border-slate-700/50">
      <label className="text-sm font-medium text-slate-400 pl-2">Sucursal:</label>
      <select
        value={selected}
        onChange={handleChange}
        className="bg-slate-950 border border-slate-700 text-slate-200 text-sm rounded-md focus:ring-blue-500 focus:border-blue-500 block px-3 py-1.5 transition-colors cursor-pointer outline-none"
      >
        <option value="ALL">🏢 Todas (Consolidado)</option>
        <option value="Matriz Quito">📍 Matriz Quito</option>
        <option value="Sucursal Guayaquil">📍 Sucursal Guayaquil</option>
        <option value="Sucursal Cuenca">📍 Sucursal Cuenca</option>
      </select>
    </div>
  );
};
