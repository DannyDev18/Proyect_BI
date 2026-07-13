import { useEffect, useRef, useState } from 'react';

interface CountUpProps {
  value: number;
  format?: (n: number) => string;
  durationMs?: number;
  className?: string;
}

const prefersReducedMotion = () =>
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/** Animación numérica de KPI (P2/P3) — ~600ms con ease-out-soft al montar/cambiar.
 * Desactivada bajo reduced-motion (muestra el valor final directo). */
export const CountUp = ({ value, format = (n) => n.toLocaleString('es-EC'), durationMs = 600, className = '' }: CountUpProps) => {
  const [display, setDisplay] = useState(prefersReducedMotion() ? value : 0);
  const fromRef = useRef(0);

  useEffect(() => {
    if (prefersReducedMotion()) {
      setDisplay(value);
      return;
    }
    const from = fromRef.current;
    const start = performance.now();
    let raf = 0;

    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs);
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplay(from + (value - from) * eased);
      if (t < 1) raf = requestAnimationFrame(tick);
      else fromRef.current = value;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, durationMs]);

  return <span className={className}>{format(display)}</span>;
};
