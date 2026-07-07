import React, { useState, useEffect } from 'react';
import { 
  Users, UserPlus, Search, Edit2, ShieldAlert, Building,
  CheckCircle2, XCircle, KeyRound 
} from 'lucide-react';
import { getUsers, createUser, updateUser, deactivateUser, activateUser, getRoles } from '../services/api';

interface UserData {
  id: number;
  nombre: string;
  email: string;
  es_activo: boolean;
  sucursal: string | null;
  id_vendedor_origen: string | null;
  role: { id: number; nombre: string };
  rol_id?: number;
}

interface RoleData {
  id: number;
  nombre: string;
}

export const UsersManagement = () => {
  const [users, setUsers] = useState<UserData[]>([]);
  const [roles, setRoles] = useState<RoleData[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  
  // Modal state
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState<'create' | 'edit'>('create');
  
  // Form state
  const [formData, setFormData] = useState({
    id: 0,
    nombre: '',
    email: '',
    password: '',
    rol_id: 2,
    sucursal: '',
    id_vendedor_origen: ''
  });

  const [formError, setFormError] = useState('');

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [usersRes, rolesRes] = await Promise.all([
        getUsers(),
        getRoles()
      ]);
      setUsers(usersRes.data);
      setRoles(rolesRes.data);
    } catch (error) {
      console.error('Error fetching users/roles:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleOpenModal = (mode: 'create' | 'edit', user?: UserData) => {
    setModalMode(mode);
    setFormError('');
    if (mode === 'edit' && user) {
      setFormData({
        id: user.id,
        nombre: user.nombre,
        email: user.email,
        password: '', // Empty password field so it doesn't edit unless typed
        rol_id: user.role.id,
        sucursal: user.sucursal || '',
        id_vendedor_origen: user.id_vendedor_origen || ''
      });
    } else {
      setFormData({
        id: 0,
        nombre: '',
        email: '',
        password: '',
        rol_id: 2,
        sucursal: '',
        id_vendedor_origen: ''
      });
    }
    setIsModalOpen(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError('');
    
    try {
      const payload: any = {
        nombre: formData.nombre,
        email: formData.email,
        rol_id: formData.rol_id,
        sucursal: formData.sucursal || null,
        id_vendedor_origen: formData.id_vendedor_origen || null
      };

      if (modalMode === 'create') {
        if (!formData.password) {
          setFormError('La contraseña es requerida.');
          return;
        }
        payload.password = formData.password;
        await createUser(payload);
      } else {
        if (formData.password) {
            payload.password = formData.password;
        }
        await updateUser(formData.id, payload);
      }
      
      setIsModalOpen(false);
      fetchData();
    } catch (error: any) {
      console.error('Error saving user:', error);
      setFormError(error.response?.data?.detail || 'Error al guardar el usuario');
    }
  };

  const handleToggleStatus = async (user: UserData) => {
    try {
      if (user.es_activo) {
        await deactivateUser(user.id);
      } else {
        await activateUser(user.id);
      }
      fetchData();
    } catch (error: any) {
      console.error('Error toggling status:', error);
      alert(error.response?.data?.detail || 'Error al cambiar estado');
    }
  };

  const filteredUsers = users.filter(u => 
    u.nombre.toLowerCase().includes(searchTerm.toLowerCase()) || 
    u.email.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="p-8 max-w-7xl mx-auto font-sans">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-8 gap-4">
        <div>
          <h1 className="text-3xl font-display font-semibold text-slate-100 flex items-center">
            <Users className="mr-3 text-blue-500" /> Gestión de Usuarios
          </h1>
          <p className="text-slate-400 mt-1">
            Administra los accesos y roles del sistema analítico.
          </p>
        </div>
        <button
          onClick={() => handleOpenModal('create')}
          className="bg-blue-600 hover:bg-blue-500 text-white px-5 py-2.5 rounded-lg font-medium transition-all flex items-center shadow-[0_0_15px_rgba(59,130,246,0.2)]"
        >
          <UserPlus size={18} className="mr-2" />
          Nuevo Usuario
        </button>
      </div>

      <div className="bg-slate-900/50 backdrop-blur-xl border border-slate-800 rounded-2xl overflow-hidden shadow-2xl">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <div className="relative w-full max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={18} />
            <input 
              type="text" 
              placeholder="Buscar por nombre o correo..." 
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              className="w-full bg-slate-950/50 border border-slate-700/50 rounded-lg pl-10 pr-4 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 placeholder-slate-500"
            />
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-400">
            <thead className="bg-slate-950/40 text-xs uppercase font-medium text-slate-500 border-b border-slate-800">
              <tr>
                <th className="px-6 py-4">Usuario</th>
                <th className="px-6 py-4">Rol & Contexto</th>
                <th className="px-6 py-4 text-center">Estado</th>
                <th className="px-6 py-4 text-right">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/50">
              {loading ? (
                <tr><td colSpan={4} className="text-center py-8 text-slate-500">Cargando usuarios...</td></tr>
              ) : filteredUsers.length === 0 ? (
                <tr><td colSpan={4} className="text-center py-8 text-slate-500">No se encontraron resultados.</td></tr>
              ) : (
                filteredUsers.map(user => (
                  <tr key={user.id} className="hover:bg-slate-800/20 transition-colors">
                    <td className="px-6 py-4">
                      <div className="flex items-center">
                        <div className="h-10 w-10 rounded-full bg-slate-800 flex items-center justify-center text-slate-300 font-bold uppercase shrink-0">
                          {user.nombre.charAt(0)}
                        </div>
                        <div className="ml-4">
                          <div className="font-medium text-slate-200">{user.nombre}</div>
                          <div className="text-slate-500 text-xs">{user.email}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center space-x-2">
                        <span className={`px-2.5 py-1 text-xs font-semibold rounded-md border 
                          ${user.role.nombre === 'administrador' ? 'bg-purple-500/10 text-purple-400 border-purple-500/20' : 
                            user.role.nombre === 'gerencia' ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' :
                            'bg-blue-500/10 text-blue-400 border-blue-500/20'}`}>
                          {user.role.nombre}
                        </span>
                        {user.sucursal && (
                          <span className="flex items-center text-xs text-slate-500">
                            <Building size={12} className="mr-1" /> {user.sucursal}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-center">
                      <button 
                        onClick={() => handleToggleStatus(user)}
                        className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium cursor-pointer transition-colors
                          ${user.es_activo ? 'bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20' : 'bg-rose-500/10 text-rose-400 hover:bg-rose-500/20'}
                        `}
                      >
                        {user.es_activo ? <CheckCircle2 size={14} className="mr-1" /> : <XCircle size={14} className="mr-1" />}
                        {user.es_activo ? 'Activo' : 'Inactivo'}
                      </button>
                    </td>
                    <td className="px-6 py-4 text-right space-x-2">
                      <button 
                        onClick={() => handleOpenModal('edit', user)}
                        className="text-slate-400 hover:text-blue-400 p-1.5 transition-colors bg-slate-800/50 hover:bg-blue-500/10 rounded-lg inline-flex items-center"
                        title="Editar"
                      >
                        <Edit2 size={16} />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modal CRUD */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-700/50 rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            <div className="p-6 border-b border-slate-800 flex justify-between items-center">
              <h3 className="text-xl font-semibold text-slate-100 flex items-center">
                {modalMode === 'create' ? <UserPlus className="mr-2 text-blue-500" /> : <Edit2 className="mr-2 text-amber-500" />}
                {modalMode === 'create' ? 'Crear Nuevo Usuario' : 'Editar Usuario'}
              </h3>
              <button onClick={() => setIsModalOpen(false)} className="text-slate-500 hover:text-slate-300">
                <XCircle size={24} />
              </button>
            </div>
            
            <div className="p-6">
              {formError && (
                <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg flex items-center text-red-400 text-sm">
                  <ShieldAlert size={16} className="mr-2 flex-shrink-0" />
                  {formError}
                </div>
              )}
              
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <label className="text-xs font-semibold uppercase text-slate-400">Nombre Completo</label>
                    <input 
                      required
                      type="text" 
                      value={formData.nombre}
                      onChange={e => setFormData({...formData, nombre: e.target.value})}
                      className="w-full bg-slate-950 border border-slate-700/50 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-semibold uppercase text-slate-400">Email</label>
                    <input 
                      required
                      type="email" 
                      value={formData.email}
                      onChange={e => setFormData({...formData, email: e.target.value})}
                      className="w-full bg-slate-950 border border-slate-700/50 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <label className="text-xs font-semibold uppercase text-slate-400">Contraseña {modalMode === 'edit' && <span className="text-slate-600 font-normal ml-1">(Opcional)</span>}</label>
                    <div className="relative">
                      <KeyRound className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" size={14} />
                      <input 
                        type="password" 
                        pattern="^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$"
                        title="Mínimo 8 caracteres, al menos una mayúscula, texto, un número y un caracter especial"
                        value={formData.password}
                        onChange={e => setFormData({...formData, password: e.target.value})}
                        className="w-full bg-slate-950 border border-slate-700/50 rounded-lg pl-8 pr-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                        placeholder={modalMode === 'edit' ? "Dejar en blanco para no cambiar" : "********"}
                      />
                    </div>
                  </div>
                  
                  <div className="space-y-1">
                    <label className="text-xs font-semibold uppercase text-slate-400">Rol Sistema</label>
                    <select
                      value={formData.rol_id}
                      onChange={e => setFormData({...formData, rol_id: parseInt(e.target.value)})}
                      className="w-full bg-slate-950 border border-slate-700/50 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 appearance-none"
                    >
                      {roles.map(r => (
                        <option key={r.id} value={r.id}>{r.nombre}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2 border-t border-slate-800">
                  <div className="space-y-1">
                    <label className="text-xs font-semibold uppercase text-slate-400">Sucursal (RLS)</label>
                    <input 
                      type="text" 
                      placeholder="Ej: GYE-01"
                      value={formData.sucursal}
                      onChange={e => setFormData({...formData, sucursal: e.target.value})}
                      className="w-full bg-slate-950 border border-slate-700/50 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 placeholder-slate-700"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-semibold uppercase text-slate-400">Código SAP (Ventas)</label>
                    <input 
                      type="text" 
                      placeholder="Ej: V001"
                      value={formData.id_vendedor_origen}
                      onChange={e => setFormData({...formData, id_vendedor_origen: e.target.value})}
                      className="w-full bg-slate-950 border border-slate-700/50 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 placeholder-slate-700"
                    />
                  </div>
                </div>
                
                <div className="flex justify-end pt-4 space-x-3">
                  <button 
                    type="button" 
                    onClick={() => setIsModalOpen(false)}
                    className="px-4 py-2 rounded-lg text-slate-300 hover:bg-slate-800 transition-colors font-medium text-sm"
                  >
                    Cancelar
                  </button>
                  <button 
                    type="submit" 
                    className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors font-medium text-sm flex items-center shadow-[0_0_15px_rgba(59,130,246,0.2)]"
                  >
                    {modalMode === 'create' ? 'Crear Usuario' : 'Guardar Cambios'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
