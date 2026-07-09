export const qk = {
  gerencia: {
    kpis: (filters: unknown) => ['gerencia', 'kpis', filters] as const,
    revenueByCategory: (filters: unknown) => ['gerencia', 'revenue-by-category', filters] as const,
    categories: () => ['gerencia', 'categorias'] as const,
    sucursales: () => ['gerencia', 'sucursales'] as const,
    vendedores: () => ['gerencia', 'vendedores'] as const,
    salesPrediction: () => ['gerencia', 'sales-prediction'] as const,
  },
  bodega: {
    kpis: () => ['bodega', 'kpis'] as const,
  },
  ventas: {
    goals: () => ['ventas', 'goals'] as const,
  },
  goals: {
    periods: () => ['goals', 'periods'] as const,
    tracking: (anio: number, mes: number) => ['goals', 'tracking', anio, mes] as const,
  },
};
