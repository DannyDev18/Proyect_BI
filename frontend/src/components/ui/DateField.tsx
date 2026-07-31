import { forwardRef, useRef, type InputHTMLAttributes } from 'react';
import { Calendar } from 'lucide-react';

interface DateFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type' | 'size'> {
  size?: 'sm' | 'md';
}

const sizes = {
  sm: 'pl-2.5 pr-8 py-1 text-xs',
  md: 'pl-3 pr-9 py-1.5 text-sm',
};

/** `<input type="date">` con icono de calendario explícito (Fase 2, docs/features/
 * plan_correcciones_integrales_sistema.md §Fase 2.1): el origen del icono invisible en
 * navegadores no-Chromium y en tema oscuro es depender del pseudo-elemento
 * `::-webkit-calendar-picker-indicator`, que no es estándar y Firefox/Safari lo
 * ignoran -- aquí el icono se renderiza siempre con lucide-react, independiente del
 * navegador, y un clic en cualquier parte del campo abre el selector nativo vía
 * `showPicker()` (con fallback silencioso a foco simple si el navegador no lo soporta,
 * p.ej. Safari < 16.4). Reemplaza los `<input type="date">` sueltos de
 * `BodegaFilterBar.tsx`, `QuickLogForm.tsx`, `DashboardAdmin.tsx`, `DashboardGerencia.tsx`. */
export const DateField = forwardRef<HTMLInputElement, DateFieldProps>(
  ({ size = 'md', className = '', ...rest }, ref) => {
    const localRef = useRef<HTMLInputElement>(null);

    const abrirSelector = () => {
      const el = localRef.current;
      if (el && typeof el.showPicker === 'function') {
        try {
          el.showPicker();
        } catch {
          el.focus();
        }
      } else {
        el?.focus();
      }
    };

    return (
      <div
        className="relative cursor-pointer"
        onClick={abrirSelector}
      >
        <input
          ref={(node) => {
            localRef.current = node;
            if (typeof ref === 'function') ref(node);
            else if (ref) ref.current = node;
          }}
          type="date"
          className={`bg-slate-950 border border-slate-700 text-slate-200 rounded-md outline-none cursor-pointer hover:border-slate-600 focus-ring [&::-webkit-calendar-picker-indicator]:opacity-0 [&::-webkit-calendar-picker-indicator]:absolute [&::-webkit-calendar-picker-indicator]:inset-0 [&::-webkit-calendar-picker-indicator]:w-full [&::-webkit-calendar-picker-indicator]:cursor-pointer ${sizes[size]} ${className}`}
          {...rest}
        />
        <Calendar
          size={size === 'sm' ? 12 : 14}
          className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500"
        />
      </div>
    );
  },
);
DateField.displayName = 'DateField';
