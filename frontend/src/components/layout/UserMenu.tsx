import { LogOut, Settings as SettingsIcon } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../../store/authStore';
import { DropdownItem, DropdownDivider } from '../ui/Dropdown';

const ROLE_LABEL: Record<string, string> = {
  administrador: 'Administrador',
  gerencia: 'Gerencia',
  ventas: 'Ventas',
  bodega: 'Bodega',
};

export const initials = (name: string) =>
  name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join('');

export const roleLabel = (role: string) => ROLE_LABEL[role] ?? role;

/** Contenido del menú de usuario (F3, D-5): compartido entre el Header y el bloque
 * de perfil al pie del Sidebar -- un solo lugar dueño de "Configuración"/"Cerrar sesión". */
export const UserMenuContent = () => {
  const { logout } = useAuthStore();
  const navigate = useNavigate();

  return (
    <>
      <DropdownItem icon={<SettingsIcon size={15} />} onClick={() => navigate('/settings')}>
        Configuración
      </DropdownItem>
      <DropdownDivider />
      <DropdownItem
        icon={<LogOut size={15} />}
        variant="danger"
        onClick={() => {
          logout();
          navigate('/login');
        }}
      >
        Cerrar sesión
      </DropdownItem>
    </>
  );
};
