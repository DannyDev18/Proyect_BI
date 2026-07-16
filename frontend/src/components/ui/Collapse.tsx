import type { ReactNode } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { collapseHeight } from '../../utils/motion';

interface CollapseProps {
  open: boolean;
  children: ReactNode;
  className?: string;
}

/** Contenedor acordeón (F2, D-4): anima altura vía Framer Motion (mide `auto`
 * internamente, sin JS de medición manual) — usado por los grupos del Sidebar. */
export const Collapse = ({ open, children, className = '' }: CollapseProps) => (
  <AnimatePresence initial={false}>
    {open && (
      <motion.div {...collapseHeight} className={`overflow-hidden ${className}`}>
        {children}
      </motion.div>
    )}
  </AnimatePresence>
);
