import { AlertOctagon } from 'lucide-react';
import { Button } from './Button';

interface ErrorStateProps {
  message?: string;
  onRetry?: () => void;
  className?: string;
}

/** Error accionable (P4) — reemplaza el texto rojo suelto por página. Explica qué pasó
 * y ofrece "Reintentar" cuando el hook expone `refetch`. */
export const ErrorState = ({ message = 'No se pudo cargar la información.', onRetry, className = '' }: ErrorStateProps) => (
  <div className={`flex flex-col items-center justify-center text-center py-12 px-6 gap-3 ${className}`}>
    <div className="p-3 rounded-xl bg-danger/10 border border-danger/20">
      <AlertOctagon size={22} className="text-danger" />
    </div>
    <p className="text-sm text-slate-300 max-w-sm">{message}</p>
    {onRetry && (
      <Button variant="ghost" size="sm" onClick={onRetry}>
        Reintentar
      </Button>
    )}
  </div>
);
