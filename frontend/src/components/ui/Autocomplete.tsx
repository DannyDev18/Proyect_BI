import { Search, X } from 'lucide-react';
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useDebouncedValue } from '../../hooks/useDebouncedValue';

interface AutocompleteProps<T> {
  placeholder?: string;
  label?: string;
  loading?: boolean;
  options: T[] | null;
  getKey: (item: T) => string;
  renderOption: (item: T) => ReactNode;
  onSelect: (item: T) => void;
  onQueryChange: (debouncedQuery: string) => void;
  minChars?: number;
  debounceMs?: number;
}

const DROPDOWN_MAX_HEIGHT = 224; // 14rem, mismo alto que el antiguo max-h-56
const VIEWPORT_MARGIN = 8;
const MIN_USABLE_HEIGHT = 100;

interface DropdownStyle extends CSSProperties {
  left: number;
  width: number;
  maxHeight: number;
}

/** Buscador en vivo: dispara `onQueryChange` (debounced) en cada tecla, sin botón de
 * submit -- a diferencia de `SearchInput`, que requiere Enter/clic. Usado por el
 * asistente de Venta Cruzada para productos y clientes (docs/auditoria/25_...md).
 *
 * El dropdown se renderiza en un portal a `document.body` con `position: fixed`,
 * calculando sus coordenadas desde el input real -- si se renderizara como hijo
 * normal, quedaría recortado por cualquier ancestro con `overflow-hidden` (p.ej.
 * `ChartCard`) o pintado debajo de un hermano posterior que crea su propio stacking
 * context (p.ej. otra tarjeta con su propia animación de entrada) -- `z-index` no
 * "escapa" de su stacking context, así que subirlo no alcanza (hallazgo de uso real).
 *
 * Además, al ser `position: fixed` (relativo al viewport, no al documento), si se
 * abre siempre hacia abajo puede quedar recortado por el borde inferior de la
 * ventana cuando el input está bajo en la página -- a diferencia de un elemento en
 * flujo normal, no hay forma de hacer scroll para revelarlo. Por eso se calcula el
 * espacio disponible arriba/abajo del input y se decide la dirección + alto máximo
 * dinámicamente (mismo patrón que un combobox de Radix/Headless UI). */
export function Autocomplete<T>({
  placeholder = 'Buscar…',
  label,
  loading = false,
  options,
  getKey,
  renderOption,
  onSelect,
  onQueryChange,
  minChars = 2,
  debounceMs = 250,
}: AutocompleteProps<T>) {
  const [texto, setTexto] = useState('');
  const [abierto, setAbierto] = useState(false);
  const [estilo, setEstilo] = useState<DropdownStyle | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const debounced = useDebouncedValue(texto, debounceMs);

  useEffect(() => {
    onQueryChange(debounced.trim().length >= minChars ? debounced.trim() : '');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced, minChars]);

  const mostrarDropdown = abierto && texto.trim().length >= minChars;

  useEffect(() => {
    if (!mostrarDropdown) return;
    const actualizarPosicion = () => {
      const rect = wrapperRef.current?.getBoundingClientRect();
      if (!rect) return;

      const espacioAbajo = window.innerHeight - rect.bottom - VIEWPORT_MARGIN;
      const espacioArriba = rect.top - VIEWPORT_MARGIN;
      const abreAbajo = espacioAbajo >= MIN_USABLE_HEIGHT || espacioAbajo >= espacioArriba;
      const espacioDisponible = abreAbajo ? espacioAbajo : espacioArriba;
      const maxHeight = Math.max(MIN_USABLE_HEIGHT, Math.min(DROPDOWN_MAX_HEIGHT, espacioDisponible));

      setEstilo(
        abreAbajo
          ? { position: 'fixed', top: rect.bottom + 4, left: rect.left, width: rect.width, maxHeight }
          : { position: 'fixed', bottom: window.innerHeight - rect.top + 4, left: rect.left, width: rect.width, maxHeight },
      );
    };
    actualizarPosicion();
    window.addEventListener('scroll', actualizarPosicion, true);
    window.addEventListener('resize', actualizarPosicion);
    return () => {
      window.removeEventListener('scroll', actualizarPosicion, true);
      window.removeEventListener('resize', actualizarPosicion);
    };
  }, [mostrarDropdown, options, loading]);

  return (
    <div className="w-full" ref={wrapperRef}>
      {label && <label className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-2 block">{label}</label>}
      <div className="relative">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
        <input
          value={texto}
          onChange={(e) => { setTexto(e.target.value); setAbierto(true); }}
          onFocus={() => setAbierto(true)}
          onBlur={() => setTimeout(() => setAbierto(false), 150)}
          placeholder={placeholder}
          className="w-full bg-slate-900 border border-slate-700 rounded-lg pl-9 pr-8 py-2.5 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/20 transition-all"
        />
        {texto && (
          <button
            type="button"
            onClick={() => { setTexto(''); setAbierto(false); }}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
          >
            <X size={13} />
          </button>
        )}
      </div>
      {mostrarDropdown && estilo && createPortal(
        <ul
          style={estilo}
          className="z-[9999] bg-slate-900 border border-slate-700 rounded-lg shadow-lg overflow-auto"
        >
          {loading ? (
            <li className="px-3 py-2 text-sm text-slate-500">Buscando…</li>
          ) : options && options.length > 0 ? (
            options.map((item) => (
              <li key={getKey(item)}>
                <button
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => { onSelect(item); setTexto(''); setAbierto(false); }}
                  className="w-full text-left px-3 py-2 hover:bg-slate-800 text-sm text-slate-200"
                >
                  {renderOption(item)}
                </button>
              </li>
            ))
          ) : (
            <li className="px-3 py-2 text-sm text-slate-500">Sin resultados</li>
          )}
        </ul>,
        document.body,
      )}
    </div>
  );
}
