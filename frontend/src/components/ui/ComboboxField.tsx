import { Check, ChevronDown, Search } from 'lucide-react';
import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { createPortal } from 'react-dom';

interface ComboboxFieldProps {
  value: string | null;
  onChange: (value: string | null) => void;
  options: string[];
  /** Etiqueta de la opción "sin filtro" (value=null), p.ej. "Todas las bodegas". */
  allLabel: string;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  'aria-label'?: string;
}

const DROPDOWN_MAX_HEIGHT = 260;
const VIEWPORT_MARGIN = 8;
const MIN_USABLE_HEIGHT = 100;

interface DropdownStyle extends CSSProperties {
  left: number;
  width: number;
  maxHeight: number;
}

/** Fase 2 §2.3 (docs/features/plan_correcciones_integrales_sistema.md): filtro
 * "híbrido texto + combobox" -- búsqueda tipeable sobre un catálogo REAL ya cargado en
 * memoria (p.ej. `almacenes`/`categorias`/`proveedores` de `GET /analytics/bodega/
 * filtros`), sin texto libre: solo se puede seleccionar una opción que exista en
 * `options`, igual que un `<select>` -- el backend de estos filtros exige un valor
 * exacto del catálogo, nunca una búsqueda parcial (a diferencia de `Autocomplete`, que
 * sí dispara búsqueda parcial contra el backend para catálogos grandes/paginados como
 * clientes o productos, docs/auditoria/25_modulo_cross_selling.md). Filtrado 100%
 * client-side porque estos catálogos ya vienen completos en la respuesta de filtros. */
export const ComboboxField = ({
  value, onChange, options, allLabel, placeholder = 'Buscar…', disabled = false, className = '',
  'aria-label': ariaLabel,
}: ComboboxFieldProps) => {
  const [abierto, setAbierto] = useState(false);
  const [texto, setTexto] = useState('');
  const [estilo, setEstilo] = useState<DropdownStyle | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const filtradas = useMemo(() => {
    const q = texto.trim().toLowerCase();
    const base = q ? options.filter((o) => o.toLowerCase().includes(q)) : options;
    const incluirTodas = !q || allLabel.toLowerCase().includes(q);
    return { incluirTodas, base };
  }, [texto, options, allLabel]);

  useEffect(() => {
    if (!abierto) return;
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
          ? { position: 'fixed', top: rect.bottom + 4, left: rect.left, width: Math.max(rect.width, 220), maxHeight }
          : { position: 'fixed', bottom: window.innerHeight - rect.top + 4, left: rect.left, width: Math.max(rect.width, 220), maxHeight },
      );
    };
    actualizarPosicion();
    window.addEventListener('scroll', actualizarPosicion, true);
    window.addEventListener('resize', actualizarPosicion);
    return () => {
      window.removeEventListener('scroll', actualizarPosicion, true);
      window.removeEventListener('resize', actualizarPosicion);
    };
  }, [abierto]);

  const abrir = () => {
    if (disabled) return;
    setTexto('');
    setAbierto(true);
    // el input del dropdown se monta vía portal en el siguiente tick
    setTimeout(() => inputRef.current?.focus(), 0);
  };

  const seleccionar = (v: string | null) => {
    onChange(v);
    setAbierto(false);
  };

  const etiquetaActual = value ?? allLabel;

  return (
    <div className="relative inline-block" ref={wrapperRef}>
      <button
        type="button"
        disabled={disabled}
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={abierto}
        onClick={abrir}
        className={`flex items-center justify-between gap-2 bg-slate-950 border border-slate-700 text-slate-300 rounded-md outline-none cursor-pointer hover:border-slate-600 focus-ring pl-3 pr-2 py-2 text-sm disabled:opacity-50 disabled:cursor-not-allowed ${className}`}
      >
        <span className={`truncate ${value ? '' : 'text-slate-400'}`}>{etiquetaActual}</span>
        <ChevronDown size={14} className="shrink-0 text-slate-500" />
      </button>

      {abierto && estilo && createPortal(
        <div style={estilo} className="z-[9999] bg-slate-900 border border-slate-700 rounded-lg shadow-lg flex flex-col overflow-hidden">
          <div className="relative shrink-0 border-b border-slate-800">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
            <input
              ref={inputRef}
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              onMouseDown={(e) => e.stopPropagation()}
              onBlur={() => setTimeout(() => setAbierto(false), 150)}
              placeholder={placeholder}
              className="w-full bg-transparent pl-8 pr-2 py-2 text-sm text-slate-200 placeholder-slate-600 outline-none"
            />
          </div>
          <ul role="listbox" className="overflow-auto">
            {filtradas.incluirTodas && (
              <li role="option" aria-selected={value === null}>
                <button
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => seleccionar(null)}
                  className="w-full flex items-center justify-between gap-2 text-left px-3 py-2 hover:bg-slate-800 text-sm text-slate-400 italic"
                >
                  {allLabel}
                  {value === null && <Check size={13} className="text-primary shrink-0" />}
                </button>
              </li>
            )}
            {filtradas.base.length === 0 && !filtradas.incluirTodas ? (
              <li className="px-3 py-2 text-sm text-slate-500">Sin resultados</li>
            ) : (
              filtradas.base.map((o) => (
                <li key={o} role="option" aria-selected={value === o}>
                  <button
                    type="button"
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => seleccionar(o)}
                    className="w-full flex items-center justify-between gap-2 text-left px-3 py-2 hover:bg-slate-800 text-sm text-slate-200"
                  >
                    <span className="truncate">{o}</span>
                    {value === o && <Check size={13} className="text-primary shrink-0" />}
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>,
        document.body,
      )}
    </div>
  );
};
