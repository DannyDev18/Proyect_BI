// Variantes compartidas de Framer Motion (F1.5 — plan_refactor_visual_signal_deck_3.md).
// Alcance acotado a presencia/salida/layout (dropdowns, modales, drawer, acordeón, listas)
// donde CSS no llega limpio; las micro-transiciones simples siguen en CSS/tokens.
// Duraciones en segundos, alineadas a la escala 120/180/250/300ms del sistema.

export const DURATION = {
  fast: 0.12,
  base: 0.25,
  slow: 0.3,
} as const;

export const EASE_OUT_SOFT = [0.16, 1, 0.3, 1] as const;

/** Fade + scale sutil — dropdowns, popovers, tooltips */
export const fadeScale = {
  initial: { opacity: 0, scale: 0.97 },
  animate: { opacity: 1, scale: 1 },
  exit: { opacity: 0, scale: 0.97 },
  transition: { duration: DURATION.fast, ease: EASE_OUT_SOFT },
};

/** Fade simple — overlays, backdrops */
export const fade = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
  transition: { duration: DURATION.base, ease: EASE_OUT_SOFT },
};

/** Slide desde la derecha — drawers */
export const slideFromRight = {
  initial: { opacity: 0, x: 24 },
  animate: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: 24 },
  transition: { duration: DURATION.slow, ease: EASE_OUT_SOFT },
};

/** Slide desde arriba — menús desplegables (Dropdown) */
export const slideFromTop = {
  initial: { opacity: 0, y: -6, scale: 0.98 },
  animate: { opacity: 1, y: 0, scale: 1 },
  exit: { opacity: 0, y: -6, scale: 0.98 },
  transition: { duration: DURATION.fast, ease: EASE_OUT_SOFT },
};

/** Acordeón por altura — grupos del Sidebar (usado junto a Collapse) */
export const collapseHeight = {
  initial: { height: 0, opacity: 0 },
  animate: { height: 'auto', opacity: 1 },
  exit: { height: 0, opacity: 0 },
  transition: { duration: DURATION.base, ease: EASE_OUT_SOFT },
};
