import { Package, Clock, ChevronRight } from 'lucide-react';
import { Badge } from '../ui/Badge';
import type { ClienteRuta, CodigoAlerta } from '../../types/cartera360';

const money = (n: number) => n.toLocaleString('es-EC', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });

const BADGE_VARIANT: Record<CodigoAlerta, 'danger' | 'warning' | 'success' | 'info' | 'primary'> = {
  riesgo_critico: 'danger',
  riesgo_medio: 'warning',
  estable: 'success',
  oportunidad: 'info',
  premium: 'primary',
  crecimiento: 'info',
};

interface PriorityCardProps {
  cliente: ClienteRuta;
  valorMaximo: number;
  onClick: () => void;
}

/** Tarjeta de prioridad (§4.2, "el corazón del refactor"): score desglosado en 2
 * medidores independientes -- NUNCA una barra apilada aditiva, porque `prioridad` es un
 * PRODUCTO (valor_historico × (1 + p_abandono/100)), no una suma (mismo criterio que
 * `ScoreDecompositionBar` de Venta Cruzada Fase 5, una representación aditiva sería
 * visualmente falsa aquí). */
export const PriorityCard = ({ cliente, valorMaximo, onClick }: PriorityCardProps) => {
  const pctValor = valorMaximo > 0 ? Math.min(100, (cliente.score_desglose.valor_historico / valorMaximo) * 100) : 0;
  const pctAbandono = Math.min(100, cliente.score_desglose.probabilidad_abandono);

  return (
    <button
      type="button"
      onClick={onClick}
      className="card card-hover w-full text-left p-5 flex flex-col gap-4 focus-ring"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-sans font-semibold text-slate-100 truncate">{cliente.nombre_cliente}</p>
          <p className="text-xs text-slate-500 font-mono">{cliente.cliente_id}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Badge variant={BADGE_VARIANT[cliente.clasificacion.codigo]}>{cliente.clasificacion.etiqueta}</Badge>
          <ChevronRight size={16} className="text-slate-600" />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <p className="text-[10px] uppercase tracking-widest text-slate-600 mb-1">Valor histórico</p>
          <div className="h-1.5 rounded-full bg-slate-800/80 overflow-hidden">
            <div className="h-full rounded-full bg-primary" style={{ width: `${pctValor}%` }} />
          </div>
          <p className="text-xs font-mono text-slate-400 mt-1">{money(cliente.valor_historico)}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-widest text-slate-600 mb-1">Prob. de abandono</p>
          <div className="h-1.5 rounded-full bg-slate-800/80 overflow-hidden">
            <div className="h-full rounded-full bg-danger" style={{ width: `${pctAbandono}%` }} />
          </div>
          <p className="text-xs font-mono text-slate-400 mt-1">{cliente.probabilidad_recompra.toFixed(0)}% prob. de recompra</p>
        </div>
      </div>

      <p className="text-xs text-slate-400 leading-relaxed">{cliente.motivo}</p>

      {cliente.oferta_sugerida && (
        <div className="flex items-center gap-2 text-xs bg-slate-800/40 border border-slate-800 rounded-lg px-3 py-2">
          <Package size={14} className="text-primary shrink-0" />
          <span className="text-slate-300 truncate">{cliente.oferta_sugerida.nombre}</span>
          <span className="font-mono text-slate-500 shrink-0">{money(cliente.oferta_sugerida.precio)}</span>
        </div>
      )}

      <div className="flex items-center justify-between text-[11px] text-slate-600">
        <span className="flex items-center gap-1">
          <Clock size={11} /> {cliente.dias_sin_comprar} días sin comprar
        </span>
        {cliente.proxima_accion_fecha && (
          <span className="text-warning">Próxima acción: {cliente.proxima_accion_fecha}</span>
        )}
      </div>
    </button>
  );
};
