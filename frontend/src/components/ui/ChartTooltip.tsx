import type { ReactNode } from 'react';

interface ChartTooltipRow {
  label: string;
  value: ReactNode;
  color?: string;
}

interface ChartTooltipProps {
  title?: ReactNode;
  rows: ChartTooltipRow[];
}

/** Panel de tooltip único para Recharts (reemplaza el `tooltipStyle` duplicado por página, P1).
 * Uso: <Tooltip content={<ChartTooltipRenderer />} /> o construir el payload manualmente
 * con `renderChartTooltip` cuando la forma del payload lo amerita. */
export const ChartTooltip = ({ title, rows }: ChartTooltipProps) => (
  <div className="glass-elevated border border-border rounded-xl p-3 shadow-xl min-w-[160px]">
    {title && <p className="font-semibold text-slate-200 text-xs mb-1.5">{title}</p>}
    <div className="space-y-1">
      {rows.map((r, i) => (
        <div key={i} className="flex items-center justify-between gap-3 text-xs">
          <span className="flex items-center gap-1.5 text-slate-400">
            {r.color && <span className="w-2 h-2 rounded-sm shrink-0" style={{ background: r.color }} />}
            {r.label}
          </span>
          <span className="font-mono text-slate-200">{r.value}</span>
        </div>
      ))}
    </div>
  </div>
);

interface RechartsTooltipPayloadItem {
  name?: string;
  value?: number | string;
  color?: string;
  payload?: Record<string, unknown>;
}

/** Adaptador directo para la prop `content` de <Tooltip> de Recharts en el caso simple
 * (una fila por serie activa). Para tooltips con forma de payload custom, seguir usando
 * `content={({ payload }) => <ChartTooltip .../>}` en la página. */
export const renderChartTooltip = (
  active: boolean | undefined,
  payload: RechartsTooltipPayloadItem[] | undefined,
  label?: ReactNode,
) => {
  if (!active || !payload?.length) return null;
  return (
    <ChartTooltip
      title={label}
      rows={payload.map((p) => ({ label: p.name ?? '', value: p.value ?? '—', color: p.color }))}
    />
  );
};
