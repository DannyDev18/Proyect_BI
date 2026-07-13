import { useEffect, useRef, useState } from 'react';
import { Bell } from 'lucide-react';
import { useNotificacionesBodega } from '../../hooks/bodega';

const prioridadStyles: Record<string, string> = {
  alta: 'border-l-red-500 bg-red-500/5',
  media: 'border-l-amber-500 bg-amber-500/5',
  baja: 'border-l-sky-500 bg-sky-500/5',
};

/** Campana de notificaciones del módulo Bodega (§4): stock crítico, agotamiento
 * proyectado, transferencias sugeridas e informe semanal. */
export const NotificationBell = () => {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const { data: notificaciones } = useNotificacionesBodega(null);

  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onClickOutside);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onClickOutside);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, []);

  const total = notificaciones?.length ?? 0;
  const altas = notificaciones?.filter((n) => n.prioridad === 'alta').length ?? 0;

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label="Notificaciones de bodega"
        aria-expanded={open}
        className="relative p-1 text-slate-400 hover:text-cyan-400 transition-colors cursor-pointer focus-ring"
      >
        <Bell size={20} />
        {total > 0 && (
          <span className={`absolute -top-1 -right-1.5 min-w-[16px] h-4 px-1 rounded-full text-[10px] font-bold flex items-center justify-center
            ${altas > 0 ? 'bg-red-500 text-white' : 'bg-amber-500 text-slate-950'}`}>
            {total > 99 ? '99+' : total}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-3 w-96 max-w-[90vw] card border border-slate-700 shadow-2xl z-50 overflow-hidden animate-fade-in">
          <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
            <h4 className="text-sm font-semibold text-slate-200">Notificaciones de Bodega</h4>
            <span className="text-xs text-slate-500">{total} alertas</span>
          </div>
          <div className="max-h-96 overflow-y-auto divide-y divide-slate-800/60">
            {total === 0 && (
              <p className="p-4 text-sm text-slate-500">Sin alertas pendientes.</p>
            )}
            {notificaciones?.map((n, i) => (
              <div key={`${n.tipo}-${n.codart ?? i}`} className={`px-4 py-3 border-l-2 ${prioridadStyles[n.prioridad] ?? ''}`}>
                <p className="text-xs text-slate-300 leading-relaxed">{n.mensaje}</p>
                <p className="text-[10px] uppercase tracking-widest text-slate-600 mt-1">
                  Prioridad {n.prioridad}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
