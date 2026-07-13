import { SearchX } from 'lucide-react';
import { Link } from 'react-router-dom';
import { EmptyState } from '../components/ui/EmptyState';
import { Button } from '../components/ui/Button';

export const NotFound = () => (
  <div className="flex items-center justify-center h-full min-h-[60vh] w-full animate-fade-in-up">
    <EmptyState
      icon={SearchX}
      title="Esta sección no existe"
      description="La página que buscas fue movida o nunca existió. Vuelve al dashboard para seguir navegando."
      action={
        <Link to="/">
          <Button variant="primary">Volver al dashboard</Button>
        </Link>
      }
    />
  </div>
);
