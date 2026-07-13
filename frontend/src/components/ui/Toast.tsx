import { CheckCircle2, X, XCircle } from 'lucide-react';
import { useToastStore } from '../../store/toastStore';

const variantStyles = {
  success: { border: 'border-emerald-500/30', icon: <CheckCircle2 size={16} className="text-emerald-400" /> },
  error: { border: 'border-red-500/30', icon: <XCircle size={16} className="text-red-400" /> },
};

/** Contenedor de toasts (P2) — esquina inferior derecha, monta una sola vez en Layout.
 * `aria-live="polite"` para lectores de pantalla. */
export const ToastContainer = () => {
  const { toasts, dismiss } = useToastStore();

  if (toasts.length === 0) return null;

  return (
    <div
      className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 w-full max-w-sm px-4 sm:px-0"
      aria-live="polite"
      role="status"
    >
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`card animate-toast-enter p-3.5 flex items-start gap-2.5 shadow-xl ${variantStyles[t.variant].border}`}
        >
          {variantStyles[t.variant].icon}
          <p className="text-sm text-slate-200 flex-1">{t.message}</p>
          <button
            type="button"
            onClick={() => dismiss(t.id)}
            aria-label="Cerrar notificación"
            className="text-slate-500 hover:text-slate-300 focus-ring rounded"
          >
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  );
};
