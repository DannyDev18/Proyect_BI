import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import type { ReactNode } from 'react';
import { X } from 'lucide-react';

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}

/** Panel lateral derecho (P2) — drill-down sin salir del dashboard. Focus trap, cierra
 * con Esc y clic fuera, pantalla completa bajo `md`. */
export const Drawer = ({ open, onClose, title, children }: DrawerProps) => {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    panelRef.current?.focus();

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
        return;
      }
      if (e.key !== 'Tab') return;
      const focusable = panelRef.current?.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])',
      );
      if (!focusable || focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      previouslyFocused?.focus();
    };
  }, [open, onClose]);

  if (!open) return null;

  // Portal a document.body: `position: fixed` solo es relativo al viewport si NINGÚN
  // ancestro tiene `transform`/`filter`/`perspective`. `Layout.tsx` envuelve cada página
  // en `.animate-route-enter` (transform: translateY), que crea un containing block
  // propio -- sin portal, este panel queda recortado/mal posicionado dentro de esa capa
  // (drawer con fondo visible pero sin contenido legible).
  return createPortal(
    <div className="fixed inset-0 z-50 flex justify-end">
      <div
        className="absolute inset-0 bg-[var(--color-bg-overlay)] backdrop-blur-sm animate-overlay-enter"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className="relative h-full w-full md:w-[440px] bg-slate-900 border-l border-slate-800 shadow-2xl animate-drawer-enter overflow-y-auto outline-none"
      >
        <div className="sticky top-0 bg-slate-900 border-b border-slate-800 px-6 py-4 flex items-center justify-between z-10">
          <h3 className="font-sans font-semibold text-slate-200 text-base">{title}</h3>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar panel"
            className="text-slate-500 hover:text-slate-300 focus-ring rounded p-1"
          >
            <X size={18} />
          </button>
        </div>
        <div className="p-6">{children}</div>
      </div>
    </div>,
    document.body,
  );
};
