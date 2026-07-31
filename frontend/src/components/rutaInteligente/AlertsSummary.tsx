import { AlertOctagon, AlertTriangle, ShieldCheck, Sparkles, Crown } from 'lucide-react';
import { EmptyState } from '../ui/EmptyState';
import type { ClienteRuta, CodigoAlerta } from '../../types/cartera360';

const CONFIG: Record<CodigoAlerta, { label: string; icon: typeof AlertOctagon; classes: string }> = {
  riesgo_critico: { label: 'Riesgo crítico', icon: AlertOctagon, classes: 'text-danger bg-danger/10 border-danger/20' },
  riesgo_medio: { label: 'Riesgo medio', icon: AlertTriangle, classes: 'text-warning bg-warning/10 border-warning/20' },
  estable: { label: 'Estable', icon: ShieldCheck, classes: 'text-success bg-success/10 border-success/20' },
  oportunidad: { label: 'Oportunidad', icon: Sparkles, classes: 'text-info bg-info/10 border-info/20' },
  premium: { label: 'Premium', icon: Crown, classes: 'text-primary bg-primary/10 border-primary/20' },
  crecimiento: { label: 'Crecimiento', icon: Sparkles, classes: 'text-info bg-info/10 border-info/20' },
};

const ORDEN: CodigoAlerta[] = ['riesgo_critico', 'riesgo_medio', 'oportunidad', 'premium', 'estable', 'crecimiento'];

interface AlertsSummaryProps {
  clientes: ClienteRuta[];
}

/** Resumen de alertas de la ruta de hoy (§4.4 del plan): triage visual rápido de las 6
 * clasificaciones deterministas que ya trae cada cliente de `/ruta/hoy` -- sin llamada
 * nueva al backend, solo agrupa lo que ya se cargó. Reemplaza a "Efectividad Comercial"
 * en esta página (esa métrica necesita volumen de gestiones que hoy no existe, D-1;
 * este resumen es útil desde el primer día). */
export const AlertsSummary = ({ clientes }: AlertsSummaryProps) => {
  if (clientes.length === 0) {
    return <EmptyState title="Sin clientes en la ruta de hoy" description="No hay alertas que resumir." />;
  }

  const conteos = clientes.reduce<Partial<Record<CodigoAlerta, number>>>((acc, c) => {
    const codigo = c.clasificacion.codigo;
    acc[codigo] = (acc[codigo] ?? 0) + 1;
    return acc;
  }, {});

  const presentes = ORDEN.filter((codigo) => conteos[codigo]);

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
      {presentes.map((codigo) => {
        const { label, icon: Icon, classes } = CONFIG[codigo];
        return (
          <div key={codigo} className={`flex items-center gap-3 rounded-lg border p-3 ${classes}`}>
            <Icon size={18} className="shrink-0" />
            <div className="min-w-0">
              <p className="text-lg font-mono font-semibold leading-none">{conteos[codigo]}</p>
              <p className="text-[11px] mt-1 truncate opacity-90">{label}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
};
