export const qk = {
  gerencia: {
    kpis: (filters: unknown) => ['gerencia', 'kpis', filters] as const,
    revenueByCategory: (filters: unknown) => ['gerencia', 'revenue-by-category', filters] as const,
    categories: () => ['gerencia', 'categorias'] as const,
    sucursales: () => ['gerencia', 'sucursales'] as const,
    vendedores: () => ['gerencia', 'vendedores'] as const,
    almacenes: () => ['gerencia', 'almacenes'] as const,
    evolucionMensual: (filters: unknown) => ['gerencia', 'evolucion-mensual', filters] as const,
    cumplimientoMeta: (anio: number, mes: number) => ['gerencia', 'cumplimiento-meta', anio, mes] as const,
  },
  bodega: {
    kpis: () => ['bodega', 'kpis'] as const,
    filtros: (categoria?: string | null) => ['bodega', 'filtros', categoria ?? null] as const,
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
    reporte: (tipo: string, filters: unknown) => ['bodega', 'reporte', tipo, filters] as const,
    prediccionComprasMes: (filters: unknown, productoCod: string | null | undefined) =>
      ['bodega', 'prediccion-compras-mes', filters, productoCod] as const,
  },
  reabastecimiento: {
    lista: (filters: unknown, extra: unknown, pagination: unknown) =>
      ['reabastecimiento', 'lista', filters, extra, pagination] as const,
    resumen: (filters: unknown, horizonte: number | null | undefined) =>
      ['reabastecimiento', 'resumen', filters, horizonte] as const,
    politica: () => ['reabastecimiento', 'politica'] as const,
    leadTimes: () => ['reabastecimiento', 'lead-times'] as const,
    alertas: (filters: unknown, horizonte: number | null | undefined) =>
      ['reabastecimiento', 'alertas', filters, horizonte] as const,
    propuestas: () => ['reabastecimiento', 'propuestas'] as const,
    propuestaDetalle: (id: number) => ['reabastecimiento', 'propuestas', id] as const,
  },
  ventas: {
    goals: (anio?: number, mes?: number) => ['ventas', 'goals', anio, mes] as const,
    myGoalTracking: () => ['ventas', 'my-goal-tracking'] as const,
    metaSugerida: () => ['ventas', 'goal-meta-sugerida'] as const,
    goalRecommendations: () => ['ventas', 'goal-recommendations'] as const,
    myCommission: () => ['ventas', 'my-commission'] as const,
    postGoalInvoices: () => ['ventas', 'post-goal-invoices'] as const,
    miNegocio: () => ['ventas', 'mi-negocio'] as const,
  },
  goals: {
    periods: () => ['goals', 'periods'] as const,
    tracking: (anio: number, mes: number, vendedor?: string | null) =>
      ['goals', 'tracking', anio, mes, vendedor ?? null] as const,
    aiSummary: () => ['goals', 'ai-summary'] as const,
    commissionTracking: (anio: number, mes: number, vendedor?: string | null) =>
      ['goals', 'commission-tracking', anio, mes, vendedor ?? null] as const,
    metaSugeridaGerencia: (vendedorOrigen: string, anio?: number | null, mes?: number | null) =>
      ['goals', 'meta-sugerida', vendedorOrigen, anio ?? null, mes ?? null] as const,
    metaConfigCatalogo: () => ['goals', 'meta-config', 'catalogo'] as const,
    metaConfigModulos: () => ['goals', 'meta-config', 'modulos'] as const,
  },
  commissionConfig: {
    matriz: () => ['commission-config', 'matriz'] as const,
    credito: () => ['commission-config', 'credito'] as const,
    vendedores: () => ['commission-config', 'vendedores'] as const,
    perfilCategorias: (meses: number) => ['commission-config', 'perfil-categorias', meses] as const,
    lineasSinCosto: (anio: number | undefined, mes: number | undefined) =>
      ['commission-config', 'lineas-sin-costo', anio, mes] as const,
    auditoria: () => ['commission-config', 'auditoria'] as const,
    searchClases: (q: string) => ['commission-config', 'search-clases', q] as const,
    searchVendedores: (q: string) => ['commission-config', 'search-vendedores', q] as const,
    tramosCobranza: () => ['commission-config', 'tramos-cobranza'] as const,
    tramosCumplimiento: () => ['commission-config', 'tramos-cumplimiento'] as const,
    formulas: () => ['commission-config', 'formulas'] as const,
  },
  cartera360: {
    listaTrabajo: () => ['cartera360', 'lista-trabajo'] as const,
    detalleCliente: (clienteId: string) => ['cartera360', 'detalle-cliente', clienteId] as const,
    tasaRecuperacion: () => ['cartera360', 'tasa-recuperacion'] as const,
  },
  ruta: {
    hoy: () => ['ruta', 'hoy'] as const,
    timeline: (clienteId: string) => ['ruta', 'timeline', clienteId] as const,
    efectividad: () => ['ruta', 'efectividad'] as const,
    planSemanal: () => ['ruta', 'plan-semanal'] as const,
    proximasAcciones: () => ['ruta', 'proximas-acciones'] as const,
  },
  notificaciones: {
    lista: () => ['notificaciones', 'lista'] as const,
    historial: (pagination: unknown) => ['notificaciones', 'historial', pagination] as const,
  },
  crossSelling: {
    sugerencias: (items: string[], clienteId: string | null | undefined) =>
      ['cross-selling', 'sugerencias', items, clienteId] as const,
    kpis: (desde: string | undefined, hasta: string | undefined) => ['cross-selling', 'kpis', desde, hasta] as const,
    productos: (q: string) => ['cross-selling', 'productos', q] as const,
    clientes: (q: string) => ['cross-selling', 'clientes', q] as const,
    perfilCliente: (clienteId: string | null) => ['cross-selling', 'perfil-cliente', clienteId] as const,
    simular: (items: string[], clienteId: string | null | undefined) =>
      ['cross-selling', 'simular', items, clienteId] as const,
    combos: (clienteId: string | null | undefined) => ['cross-selling', 'combos', clienteId] as const,
    explicacionChurn: (clienteId: string | null) => ['cross-selling', 'explicacion-churn', clienteId] as const,
  },
};
