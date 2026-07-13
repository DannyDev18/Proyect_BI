import { Link } from 'react-router-dom';
import { ShieldAlert } from 'lucide-react';
import { EmptyState } from '../components/ui/EmptyState';
import { Button } from '../components/ui/Button';

export const AccessDenied = () => (
  <div className="flex items-center justify-center h-full min-h-[60vh] w-full animate-fade-in-up">
    <EmptyState
      icon={ShieldAlert}
      title="No tienes acceso a esta sección"
      description="Tu rol no tiene los privilegios necesarios para ver esta información. El intento quedó registrado en los logs de seguridad."
      action={
        <Link to="/">
          <Button variant="ghost">Volver al inicio</Button>
        </Link>
      }
    />
  </div>
);
