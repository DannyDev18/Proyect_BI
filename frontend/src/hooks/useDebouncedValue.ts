import { useEffect, useState } from 'react';

/** Retrasa la propagación de `value` hasta que el usuario deja de escribir por
 * `delayMs` -- usado por los autocompletar de producto/cliente del asistente de
 * Venta Cruzada para no disparar una request por cada tecla. */
export const useDebouncedValue = <T,>(value: T, delayMs = 250): T => {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);

  return debounced;
};
