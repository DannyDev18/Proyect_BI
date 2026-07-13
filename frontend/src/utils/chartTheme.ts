// Tema único para todos los gráficos Recharts del proyecto (P1: cierra la fuga de hex
// hardcodeados por página — docs/features/plan_refactor_ui.md §2.1/§3). Recharts exige
// strings planos en varias props (no siempre acepta var(--token)), así que los valores
// de @theme en index.css se resuelven una sola vez aquí.

export const CHART_PALETTE = [
  '#3b82f6', // --color-chart-1
  '#0ea472', // --color-chart-2
  '#f5b135', // --color-chart-3
  '#a78bfa', // --color-chart-4
  '#e84f9c', // --color-chart-5
  '#0891b2', // --color-chart-6
  '#f2872e', // --color-chart-7
  '#9acd32', // --color-chart-8
] as const;

/** @deprecated usar CHART_PALETTE */
export const COLORS = CHART_PALETTE;

export const chartTheme = {
  grid: '#1e293b',
  axis: '#64748b',
  axisLabel: '#94a3b8',
  live: '#22d3ee',
  ml: '#f5b135',
  danger: '#ef4444',
  success: '#10b981',
  cursor: '#1e293b',
  cardBg: '#0f172a', // --color-bg-surface — borde de activeDot para que "flote" sobre la card
  needle: '#f8fafc', // --color-text-primary — aguja/pivote de gauges D3
  median: '#475569', // slate-600 — líneas de referencia (mediana/promedio), distinto del grid
  palette: CHART_PALETTE,
} as const;

export const colorByIndex = (index: number) => CHART_PALETTE[Math.max(0, index) % CHART_PALETTE.length];

export const colorByCategory = (categoria: string, categorias: string[]) =>
  colorByIndex(categorias.indexOf(categoria));

export const axisTick = { fill: chartTheme.axis, fontSize: 11 } as const;
export const axisTickSmall = { fill: chartTheme.axis, fontSize: 10 } as const;
export const axisTickLabel = { fill: chartTheme.axisLabel, fontSize: 10 } as const;

/** @deprecated usar <ChartTooltip /> (components/ui/ChartTooltip.tsx) como `content` de <Tooltip> */
export const chartTooltipStyle = {
  contentStyle: {
    backgroundColor: '#0f172a',
    borderColor: '#1e293b',
    borderRadius: '10px',
    color: '#f1f5f9',
    fontSize: '12px',
  },
};
