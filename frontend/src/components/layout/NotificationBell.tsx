import { useEffect, useRef, useState } from 'react';
import { Bell, Check, CheckCheck } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useMarcarNotificacionLeida, useMarcarTodasLeidas, useNotificaciones } from '../../hooks/useNotificaciones';

const prioridadStyles: Record<string, string> = {
  alta: 'border-l-danger bg-danger/5',
  media: 'border-l-warning bg-warning/5',
  baja: 'border-l-info bg-info/5',
};

/** Campana global de notificaciones (docs/features/plan_modulo_notificaciones.md §5.1,
 * docs/auditoria/31_modulo_notificaciones.md), generalizada del patrón de Bodega a los
 * 4 roles: el backend ya segmenta por rol/usuario del JWT (`GET /notificaciones`), este
 * componente solo renderiza el payload. */
export const NotificationBell = () => {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const { data: notificaciones } = useNotificaciones();
  const marcarLeida = useMarcarNotificacionLeida();
  const marcarTodas = useMarcarTodasLeidas();

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

  const noLeidas = notificaciones.filter((n) => !n.leida);
  const total = noLeidas.length;
  const altas = noLeidas.filter((n) => n.prioridad === 'alta').length;
  const hayPersistidasNoLeidas = noLeidas.some((n) => n.persistida && n.id !== null);

  const handleAccion = (accionUrl: string | null, id: number | null) => {
    if (id !== null) marcarLeida.mutate(id);
    if (accionUrl) {
      navigate(accionUrl);
      setOpen(false);
    }
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label="Notificaciones"
        aria-expanded={open}
        className="relative p-1 text-slate-400 hover:text-primary transition-colors cursor-pointer focus-ring"
      >
        <Bell size={20} />
        {total > 0 && (
          <span className={`absolute -top-1 -right-1.5 min-w-[16px] h-4 px-1 rounded-full text-[10px] font-bold flex items-center justify-center
            ${altas > 0 ? 'bg-danger text-white' : 'bg-warning text-slate-950'}`}>
            {total > 99 ? '99+' : total}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-3 w-96 max-w-[90vw] card border border-slate-700 shadow-2xl z-50 overflow-hidden animate-fade-in">
          <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
            <h4 className="text-sm font-semibold text-slate-200">Notificaciones</h4>
            <div className="flex items-center gap-3">
              <span className="text-xs text-slate-500">{total} sin leer</span>
              {hayPersistidasNoLeidas && (
                <button
                  onClick={() => marcarTodas.mutate()}
                  className="text-xs text-primary hover:text-accent flex items-center gap-1 cursor-pointer focus-ring"
                  aria-label="Marcar todas como leídas"
                >
                  <CheckCheck size={12} /> Marcar todas
                </button>
              )}
            </div>
          </div>
          <div className="max-h-96 overflow-y-auto divide-y divide-slate-800/60">
            {notificaciones.length === 0 && (
              <p className="p-4 text-sm text-slate-500">Sin alertas pendientes.</p>
            )}
            {notificaciones.map((n, i) => (
              <div
                key={n.id ?? `${n.tipo_evento}-${i}`}
                className={`px-4 py-3 border-l-2 ${prioridadStyles[n.prioridad] ?? ''} ${n.leida ? 'opacity-60' : ''}`}
              >
                <p className="text-xs font-medium text-slate-200">{n.titulo}</p>
                <p className="text-xs text-slate-300 leading-relaxed mt-0.5">{n.mensaje}</p>
                <div className="flex items-center justify-between mt-1.5">
                  <p className="text-[10px] uppercase tracking-widest text-slate-600">
                    Prioridad {n.prioridad}
                  </p>
                  <div className="flex items-center gap-3">
                    {n.accion_url && (
                      <button
                        onClick={() => handleAccion(n.accion_url, n.id)}
                        className="text-[11px] text-primary hover:text-accent cursor-pointer focus-ring"
                      >
                        Ver
                      </button>
                    )}
                    {n.persistida && n.id !== null && !n.leida && (
                      <button
                        onClick={() => marcarLeida.mutate(n.id as number)}
                        aria-label="Marcar como leída"
                        className="text-slate-500 hover:text-success cursor-pointer focus-ring"
                      >
                        <Check size={13} />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
