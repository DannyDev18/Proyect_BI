import type { ReactNode } from 'react';
import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { slideFromTop } from '../../utils/motion';

interface DropdownProps {
  trigger: (props: { open: boolean; toggle: () => void }) => ReactNode;
  children: ReactNode;
  align?: 'start' | 'end';
  className?: string;
  panelClassName?: string;
}

/** Menú desplegable accesible (F2, D-4): cierre por click-fuera/Escape, navegación
 * por flechas entre `[role="menuitem"]`, usado por el menú de usuario (F3) y las
 * acciones agrupadas de fila en tablas (F5). */
export const Dropdown = ({ trigger, children, align = 'start', className = '', panelClassName = '' }: DropdownProps) => {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const toggle = () => setOpen((o) => !o);
  const close = () => setOpen(false);

  useEffect(() => {
    if (!open) return;

    const onClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) close();
    };

    const menuItems = () => Array.from(panelRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not([disabled])') ?? []);

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        close();
        return;
      }
      const items = menuItems();
      if (items.length === 0) return;
      const currentIndex = items.indexOf(document.activeElement as HTMLElement);
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        items[(currentIndex + 1) % items.length]?.focus();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        items[(currentIndex - 1 + items.length) % items.length]?.focus();
      } else if (e.key === 'Home') {
        e.preventDefault();
        items[0]?.focus();
      } else if (e.key === 'End') {
        e.preventDefault();
        items[items.length - 1]?.focus();
      }
    };

    document.addEventListener('mousedown', onClickOutside);
    document.addEventListener('keydown', onKeyDown);
    // Foco inicial en el primer ítem al abrir (navegación por teclado desde el trigger).
    requestAnimationFrame(() => menuItems()[0]?.focus());
    return () => {
      document.removeEventListener('mousedown', onClickOutside);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  return (
    <div className={`relative inline-block ${className}`} ref={ref}>
      {trigger({ open, toggle })}
      <AnimatePresence>
        {open && (
          <motion.div
            {...slideFromTop}
            ref={panelRef}
            role="menu"
            className={`absolute z-50 mt-2 min-w-[200px] rounded-xl border border-border glass-elevated shadow-2xl overflow-hidden py-1.5
              ${align === 'end' ? 'right-0' : 'left-0'} ${panelClassName}`}
            onClick={(e) => {
              const target = (e.target as HTMLElement).closest('[role="menuitem"]');
              if (target) close();
            }}
          >
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

interface DropdownItemProps {
  children: ReactNode;
  onClick?: () => void;
  icon?: ReactNode;
  variant?: 'default' | 'danger';
  disabled?: boolean;
}

export const DropdownItem = ({ children, onClick, icon, variant = 'default', disabled = false }: DropdownItemProps) => (
  <button
    type="button"
    role="menuitem"
    disabled={disabled}
    onClick={onClick}
    className={`w-full flex items-center gap-2.5 px-3.5 py-2 text-sm text-left transition-colors duration-fast cursor-pointer
      focus-ring disabled:opacity-40 disabled:cursor-not-allowed
      ${variant === 'danger' ? 'text-danger hover:bg-danger/10' : 'text-slate-300 hover:bg-bg-hover hover:text-text-primary'}`}
  >
    {icon}
    {children}
  </button>
);

export const DropdownDivider = () => <div className="my-1.5 border-t border-border" role="separator" />;
