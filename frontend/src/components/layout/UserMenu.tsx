import { LogOut, Settings as SettingsIcon } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { cerrarSesion } from '../../services/session';
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
          // Auditoría 43 (H43-8..H43-12): único punto de cierre de sesión -- nunca llamar
          // a useAuthStore.logout() directo, o queda caché/estado del usuario anterior.
          void cerrarSesion().then(() => navigate('/login'));
        }}
      >
        Cerrar sesión
      </DropdownItem>
    </>
  );
};
