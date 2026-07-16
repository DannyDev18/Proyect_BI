import { useEffect, useState } from 'react';
import {
  Users, UserPlus, Search, Edit2, ShieldAlert, Building,
  CheckCircle2, XCircle, KeyRound,
} from 'lucide-react';
import { getUsers, createUser, updateUser, deactivateUser, activateUser, getRoles, getAlmacenes } from '../services/users';
import type { UserData, RoleData, AlmacenOption } from '../types/admin';
import { Button } from '../components/ui/Button';
import { Select } from '../components/ui/Select';
import { Input } from '../components/ui/Input';
import { FormField } from '../components/ui/FormField';
import { DataTable, type DataTableColumn } from '../components/ui/DataTable';
import { Drawer } from '../components/ui/Drawer';
import { ConfirmDialog } from '../components/ui/ConfirmDialog';
import { useToast } from '../store/toastStore';

const roleBadge: Record<string, string> = {
  administrador: 'bg-accent/10 text-accent border-accent/20',
  gerencia: 'bg-warning/10 text-warning border-warning/20',
};

const emptyForm = {
  id: 0,
  nombre: '',
  email: '',
  password: '',
  rol_id: 0,
  sucursal: '',
  id_vendedor_origen: '',
  codalm: '',
  todos_los_almacenes: false,
};

// Rol de menor privilegio para preseleccionar "Nuevo usuario" (docs/auditoria/
// 36_actualizacion_modulo_admin.md, H5): antes se hardcodeaba rol_id=2
// ("administrador" en el seed actual), otorgando privilegios de admin por defecto
// a cualquier creación apresurada. Se resuelve por nombre del catálogo real
// (GET /roles), nunca por un id fijo.
const ROL_DEFAULT_NOMBRE = 'ventas';

export const UsersManagement = () => {
  const [users, setUsers] = useState<UserData[]>([]);
  const [roles, setRoles] = useState<RoleData[]>([]);
  const [almacenes, setAlmacenes] = useState<AlmacenOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const toast = useToast();

  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [modalMode, setModalMode] = useState<'create' | 'edit'>('create');
  const [formData, setFormData] = useState(emptyForm);
  const [formError, setFormError] = useState('');
  const [saving, setSaving] = useState(false);

  const [toToggle, setToToggle] = useState<UserData | null>(null);
  const [toggling, setToggling] = useState(false);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      setLoadError('');
      const [usersRes, rolesRes, almacenesRes] = await Promise.all([getUsers(), getRoles(), getAlmacenes()]);
      setUsers(usersRes.data);
      setRoles(rolesRes.data);
      setAlmacenes(almacenesRes.data);
    } catch (error) {
      console.error('Error fetching users/roles:', error);
      setLoadError('No se pudo cargar la lista de usuarios.');
    } finally {
      setLoading(false);
    }
  };

  const handleOpenDrawer = (mode: 'create' | 'edit', user?: UserData) => {
    setModalMode(mode);
    setFormError('');
    if (mode === 'edit' && user) {
      setFormData({
        id: user.id,
        nombre: user.nombre,
        email: user.email,
        password: '',
        rol_id: user.role.id,
        sucursal: user.sucursal || '',
        id_vendedor_origen: user.id_vendedor_origen || '',
        codalm: user.codalm || '',
        todos_los_almacenes: user.role.nombre === 'bodega' && !user.codalm,
      });
    } else {
      const rolDefault = roles.find((r) => r.nombre === ROL_DEFAULT_NOMBRE) ?? roles[0];
      setFormData({ ...emptyForm, rol_id: rolDefault?.id ?? 0 });
    }
    setIsDrawerOpen(true);
  };

  const selectedRoleNombre = roles.find((r) => r.id === formData.rol_id)?.nombre;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError('');
    setSaving(true);

    try {
      const payload: any = {
        nombre: formData.nombre,
        email: formData.email,
        rol_id: formData.rol_id,
        sucursal: null,
        id_vendedor_origen: null,
        codalm: null,
      };

      if (selectedRoleNombre === 'ventas') {
        payload.id_vendedor_origen = formData.id_vendedor_origen || null;
      } else if (selectedRoleNombre === 'bodega') {
        payload.todos_los_almacenes = formData.todos_los_almacenes;
        payload.codalm = formData.todos_los_almacenes ? null : (formData.codalm || null);
      } else {
        payload.sucursal = formData.sucursal || null;
      }

      if (modalMode === 'create') {
        if (!formData.password) {
          setFormError('La contraseña es requerida.');
          setSaving(false);
          return;
        }
        payload.password = formData.password;
        await createUser(payload);
        toast(`Usuario ${formData.nombre} creado correctamente.`, 'success');
      } else {
        if (formData.password) payload.password = formData.password;
        await updateUser(formData.id, payload);
        toast(`Usuario ${formData.nombre} actualizado correctamente.`, 'success');
      }

      setIsDrawerOpen(false);
      fetchData();
    } catch (error: any) {
      console.error('Error saving user:', error);
      setFormError(error.response?.data?.detail || 'No se pudo guardar el usuario. Verifica los datos e intenta de nuevo.');
    } finally {
      setSaving(false);
    }
  };

  const confirmToggleStatus = async () => {
    if (!toToggle) return;
    setToggling(true);
    try {
      if (toToggle.es_activo) {
        await deactivateUser(toToggle.id);
        toast(`Usuario ${toToggle.nombre} desactivado.`, 'success');
      } else {
        await activateUser(toToggle.id);
        toast(`Usuario ${toToggle.nombre} activado.`, 'success');
      }
      setToToggle(null);
      fetchData();
    } catch (error: any) {
      console.error('Error toggling status:', error);
      toast(error.response?.data?.detail || 'No se pudo cambiar el estado del usuario.', 'error');
    } finally {
      setToggling(false);
    }
  };

  const filteredUsers = users.filter((u) =>
    u.nombre.toLowerCase().includes(searchTerm.toLowerCase()) ||
    u.email.toLowerCase().includes(searchTerm.toLowerCase()));

  const columns: DataTableColumn<UserData>[] = [
    {
      key: 'usuario', header: 'Usuario',
      sortable: true,
      sortAccessor: (u) => u.nombre.toLowerCase(),
      render: (u) => (
        <div className="flex items-center">
          <div className="h-10 w-10 rounded-full bg-slate-800 flex items-center justify-center text-slate-300 font-bold uppercase shrink-0">
            {u.nombre.charAt(0)}
          </div>
          <div className="ml-4">
            <div className="font-medium text-slate-200">{u.nombre}</div>
            <div className="text-slate-500 text-xs">{u.email}</div>
          </div>
        </div>
      ),
    },
    {
      key: 'rol', header: 'Rol & Contexto',
      sortable: true,
      sortAccessor: (u) => u.role.nombre,
      render: (u) => (
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`px-2.5 py-1 text-xs font-semibold rounded-md border ${roleBadge[u.role.nombre] ?? 'bg-info/10 text-info border-info/20'}`}>
            {u.role.nombre}
          </span>
          {u.sucursal && (
            <span className="flex items-center text-xs text-slate-400">
              <Building size={12} className="mr-1" /> {u.sucursal}
            </span>
          )}
          {u.id_vendedor_origen && (
            <span className="flex items-center text-xs text-slate-400">
              <Building size={12} className="mr-1" /> Vendedor {u.id_vendedor_origen}
            </span>
          )}
          {u.role.nombre === 'bodega' && (
            <span className="flex items-center text-xs text-slate-400">
              <Building size={12} className="mr-1" /> {u.codalm ? `Almacén ${u.codalm}` : 'Todos los almacenes'}
            </span>
          )}
        </div>
      ),
    },
    {
      key: 'estado', header: 'Estado',
      sortable: true,
      sortAccessor: (u) => (u.es_activo ? 1 : 0),
      render: (u) => (
        <button
          type="button"
          onClick={() => setToToggle(u)}
          aria-label={u.es_activo ? `Desactivar a ${u.nombre}` : `Activar a ${u.nombre}`}
          className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium cursor-pointer transition-colors focus-ring
            ${u.es_activo ? 'bg-success/10 text-success hover:bg-success/20' : 'bg-danger/10 text-danger hover:bg-danger/20'}`}
        >
          {u.es_activo ? <CheckCircle2 size={14} className="mr-1" /> : <XCircle size={14} className="mr-1" />}
          {u.es_activo ? 'Activo' : 'Inactivo'}
        </button>
      ),
    },
    {
      key: 'acciones', header: 'Acciones',
      render: (u) => (
        <Button variant="ghost" size="sm" icon={<Edit2 size={14} />} onClick={() => handleOpenDrawer('edit', u)}>
          Editar
        </Button>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h1 className="text-3xl font-display font-semibold text-slate-100 flex items-center">
            <Users className="mr-3 text-info" /> Gestión de Usuarios
          </h1>
          <p className="text-slate-400 mt-1">Administra los accesos y roles del sistema analítico.</p>
        </div>
        <Button variant="primary" icon={<UserPlus size={18} />} onClick={() => handleOpenDrawer('create')}>
          Nuevo usuario
        </Button>
      </div>

      <div className="card p-4">
        <div className="w-full max-w-sm">
          <label htmlFor="users-search" className="sr-only">Buscar por nombre o correo</label>
          <Input
            id="users-search"
            type="text"
            placeholder="Buscar por nombre o correo…"
            iconLeft={<Search size={18} />}
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
      </div>

      <DataTable
        columns={columns}
        data={filteredUsers}
        rowKey={(u) => u.id}
        loading={loading}
        error={loadError || undefined}
        onRetry={fetchData}
        emptyTitle="Sin usuarios que mostrar"
        emptyDescription="Ajusta la búsqueda o crea el primer usuario del sistema."
        maxHeight="max-h-none"
        responsive
      />

      <Drawer open={isDrawerOpen} onClose={() => setIsDrawerOpen(false)} title={modalMode === 'create' ? 'Crear nuevo usuario' : 'Editar usuario'}>
        {formError && (
          <div role="alert" className="mb-4 p-3 bg-danger/10 border border-danger/20 rounded-lg flex items-center text-danger text-sm">
            <ShieldAlert size={16} className="mr-2 flex-shrink-0" />
            {formError}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <FormField label="Nombre completo" htmlFor="user-nombre" required>
            <Input
              id="user-nombre" required type="text"
              value={formData.nombre}
              onChange={(e) => setFormData({ ...formData, nombre: e.target.value })}
            />
          </FormField>

          <FormField label="Email" htmlFor="user-email" required>
            <Input
              id="user-email" required type="email"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
            />
          </FormField>

          <FormField
            label="Contraseña"
            htmlFor="user-password"
            helper={modalMode === 'edit' ? 'Opcional — dejar en blanco para no cambiar' : undefined}
          >
            <Input
              id="user-password" type="password"
              iconLeft={<KeyRound size={14} />}
              pattern="^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$"
              title="Mínimo 8 caracteres, al menos una mayúscula, una minúscula, un número y un carácter especial"
              value={formData.password}
              onChange={(e) => setFormData({ ...formData, password: e.target.value })}
              placeholder={modalMode === 'edit' ? 'Dejar en blanco para no cambiar' : '••••••••'}
            />
          </FormField>

          <FormField label="Rol del sistema" htmlFor="user-rol">
            <Select
              id="user-rol"
              className="w-full"
              value={formData.rol_id}
              onChange={(e) => setFormData({ ...formData, rol_id: parseInt(e.target.value, 10) })}
            >
              {roles.map((r) => <option key={r.id} value={r.id}>{r.nombre}</option>)}
            </Select>
          </FormField>

          <div className="pt-2 border-t border-slate-800 space-y-4">
            {selectedRoleNombre === 'ventas' && (
              <FormField
                label="Código de vendedor (codven)"
                htmlFor="user-vendedor"
                required
                helper="Se valida contra el EDW: el vendedor debe existir y estar activo. La cuenta queda enlazada automáticamente a ese vendedor."
              >
                <Input
                  id="user-vendedor" type="text" required placeholder="Ej: V001"
                  value={formData.id_vendedor_origen}
                  onChange={(e) => setFormData({ ...formData, id_vendedor_origen: e.target.value })}
                />
              </FormField>
            )}

            {selectedRoleNombre === 'bodega' && (
              <div className="space-y-3">
                <label className="flex items-center gap-2 text-sm text-slate-300">
                  <input
                    type="checkbox"
                    checked={formData.todos_los_almacenes}
                    onChange={(e) => setFormData({ ...formData, todos_los_almacenes: e.target.checked })}
                    className="rounded border-slate-700 bg-slate-950 text-primary focus-ring"
                  />
                  Acceso a todos los almacenes
                </label>
                {!formData.todos_los_almacenes && (
                  <FormField
                    label="Almacén asignado"
                    htmlFor="user-almacen"
                    required
                    helper="La cuenta solo podrá ver el almacén seleccionado."
                  >
                    <Select
                      id="user-almacen"
                      required
                      className="w-full"
                      value={formData.codalm}
                      onChange={(e) => setFormData({ ...formData, codalm: e.target.value })}
                    >
                      <option value="">Seleccionar almacén…</option>
                      {almacenes.map((a) => (
                        <option key={a.codalm} value={a.codalm}>{a.nombre_almacen} ({a.codalm})</option>
                      ))}
                    </Select>
                  </FormField>
                )}
              </div>
            )}

            {selectedRoleNombre !== 'ventas' && selectedRoleNombre !== 'bodega' && (
              <FormField label="Sucursal (RLS)" htmlFor="user-sucursal">
                <Input
                  id="user-sucursal" type="text" placeholder="Ej: GYE-01"
                  value={formData.sucursal}
                  onChange={(e) => setFormData({ ...formData, sucursal: e.target.value })}
                />
              </FormField>
            )}
          </div>

          <div className="flex justify-end pt-4 gap-3">
            <Button type="button" variant="ghost" onClick={() => setIsDrawerOpen(false)}>Cancelar</Button>
            <Button type="submit" variant="primary" loading={saving}>
              {modalMode === 'create' ? 'Crear usuario' : 'Guardar cambios'}
            </Button>
          </div>
        </form>
      </Drawer>

      <ConfirmDialog
        open={toToggle != null}
        title={toToggle?.es_activo ? 'Desactivar usuario' : 'Activar usuario'}
        message={toToggle?.es_activo
          ? <>Se revocará el acceso de <strong className="text-slate-300">{toToggle.nombre}</strong> a la plataforma. Puedes reactivarlo en cualquier momento.</>
          : <>Se restaurará el acceso de <strong className="text-slate-300">{toToggle?.nombre}</strong> a la plataforma.</>}
        confirmLabel={toToggle?.es_activo ? 'Desactivar usuario' : 'Activar usuario'}
        loading={toggling}
        onConfirm={confirmToggleStatus}
        onCancel={() => setToToggle(null)}
      />
    </div>
  );
};
