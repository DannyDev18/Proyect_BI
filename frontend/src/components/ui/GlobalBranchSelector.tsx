import { useState } from 'react';
import { useAuthStore } from '../../store/authStore';
import { useSucursales } from '../../hooks/gerencia';
import { Select } from './Select';

export const GlobalBranchSelector = ({ onSelectSucursal }: { onSelectSucursal: (sucursalId: string | null) => void }) => {
  const { user } = useAuthStore();
  const [selected, setSelected] = useState<string>('ALL');
  const { data: sucursales } = useSucursales();

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
    <div className="flex items-center space-x-2 animate-fade-in bg-slate-900 p-1.5 rounded-lg border border-slate-700/50">
      <label htmlFor="global-branch-selector" className="text-sm font-medium text-slate-400 pl-2">Sucursal:</label>
      <Select id="global-branch-selector" value={selected} onChange={handleChange}>
        <option value="ALL">Todas (Consolidado)</option>
        {sucursales?.map((sucursal) => (
          <option key={sucursal} value={sucursal}>{sucursal}</option>
        ))}
      </Select>
    </div>
  );
};
