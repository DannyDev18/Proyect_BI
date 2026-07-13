import type { LucideIcon } from 'lucide-react';
import { Inbox } from 'lucide-react';
import type { ReactNode } from 'react';

interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}

/** Vacío accionable (P4) — reemplaza filas grises "sin resultados". Dice qué hacer,
 * no solo que no hay datos. */
export const EmptyState = ({ icon: Icon = Inbox, title, description, action, className = '' }: EmptyStateProps) => (
  <div className={`flex flex-col items-center justify-center text-center py-12 px-6 gap-3 ${className}`}>
    <div className="p-3 rounded-xl bg-slate-800/40 border border-slate-800">
      <Icon size={22} className="text-slate-500" />
    </div>
    <div>
      <p className="text-sm font-semibold text-slate-300">{title}</p>
      {description && <p className="text-xs text-slate-500 mt-1 max-w-xs">{description}</p>}
    </div>
    {action}
  </div>
);
