export const qk = {
  gerencia: {
    kpis: (filters: unknown) => ['gerencia', 'kpis', filters] as const,
    revenueByCategory: (filters: unknown) => ['gerencia', 'revenue-by-category', filters] as const,
    categories: () => ['gerencia', 'categorias'] as const,
    sucursales: () => ['gerencia', 'sucursales'] as const,
    vendedores: () => ['gerencia', 'vendedores'] as const,
    almacenes: () => ['gerencia', 'almacenes'] as const,
    salesPrediction: (filters: unknown) => ['gerencia', 'sales-prediction', filters] as const,
  },
  bodega: {
    kpis: () => ['bodega', 'kpis'] as const,
    filtros: () => ['bodega', 'filtros'] as const,
    kpisDashboard: (filters: unknown) => ['bodega', 'kpis-dashboard', filters] as const,
    salidasForecast: (filters: unknown, producto: string | null) => ['bodega', 'salidas-forecast', filters, producto] as const,
    rotacionMatriz: (filters: unknown) => ['bodega', 'rotacion-matriz', filters] as const,
    topProductos: (filters: unknown) => ['bodega', 'top-productos', filters] as const,
    salidasCategoria: (filters: unknown) => ['bodega', 'salidas-categoria', filters] as const,
    stockReorden: (filters: unknown, soloCriticos: boolean, pagination: unknown) =>
      ['bodega', 'stock-reorden', filters, soloCriticos, pagination] as const,
    necesidadCompra: (filters: unknown, horizonte: number | undefined, pagination: unknown) =>
      ['bodega', 'necesidad-compra', filters, horizonte, pagination] as const,
    inventarioMatriz: (filters: unknown, estado: string | null, pagination: unknown) =>
      ['bodega', 'inventario-matriz', filters, estado, pagination] as const,
    transferencias: (filters: unknown, pagination: unknown) =>
      ['bodega', 'transferencias', filters, pagination] as const,
    notificaciones: (almacen: string | null) => ['bodega', 'notificaciones', almacen] as const,
    reporte: (tipo: string, filters: unknown) => ['bodega', 'reporte', tipo, filters] as const,
    prediccionComprasMes: (filters: unknown, productoCod: string | null | undefined) =>
      ['bodega', 'prediccion-compras-mes', filters, productoCod] as const,
  },
  ventas: {
    goals: () => ['ventas', 'goals'] as const,
    myGoalTracking: () => ['ventas', 'my-goal-tracking'] as const,
    forecastCierre: () => ['ventas', 'goal-forecast-cierre'] as const,
    metaSugerida: () => ['ventas', 'goal-meta-sugerida'] as const,
    goalRecommendations: () => ['ventas', 'goal-recommendations'] as const,
    myCommission: () => ['ventas', 'my-commission'] as const,
    postGoalInvoices: () => ['ventas', 'post-goal-invoices'] as const,
  },
  goals: {
    periods: () => ['goals', 'periods'] as const,
    tracking: (anio: number, mes: number) => ['goals', 'tracking', anio, mes] as const,
    aiSummary: () => ['goals', 'ai-summary'] as const,
    commissionTracking: (anio: number, mes: number) => ['goals', 'commission-tracking', anio, mes] as const,
  },
  commissionConfig: {
    matriz: () => ['commission-config', 'matriz'] as const,
    credito: () => ['commission-config', 'credito'] as const,
    vendedores: () => ['commission-config', 'vendedores'] as const,
    perfilCategorias: (meses: number) => ['commission-config', 'perfil-categorias', meses] as const,
    lineasSinCosto: (anio: number | undefined, mes: number | undefined) =>
      ['commission-config', 'lineas-sin-costo', anio, mes] as const,
  },
  cartera360: {
    listaTrabajo: () => ['cartera360', 'lista-trabajo'] as const,
    detalleCliente: (clienteId: string) => ['cartera360', 'detalle-cliente', clienteId] as const,
    tasaRecuperacion: () => ['cartera360', 'tasa-recuperacion'] as const,
  },
  crossSelling: {
    sugerencias: (items: string[], clienteId: string | null | undefined) =>
      ['cross-selling', 'sugerencias', items, clienteId] as const,
    kpis: (desde: string | undefined, hasta: string | undefined) => ['cross-selling', 'kpis', desde, hasta] as const,
    topCombinaciones: () => ['cross-selling', 'top-combinaciones'] as const,
    productos: (q: string) => ['cross-selling', 'productos', q] as const,
    clientes: (q: string) => ['cross-selling', 'clientes', q] as const,
  },
};
