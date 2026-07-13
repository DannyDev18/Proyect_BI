// Tipos del módulo Bodega — contratos de backend/app/schemas/warehouse.py
// (docs/features/modulo_bodega.md, auditoría 23; paginación: auditoría 24).
import type { Page } from './pagination';

// ── Legado (endpoints /kpis-inventory y /demand-forecasting) ────────────────
export interface BodegaKPIs {
  items_riesgo_desabastecimiento: number;
  items_sobrestock: number;
  valorizacion_inventario: number;
  rotacion_mensual: number;
  alertas_criticas?: number;
}

export interface DemandaResponse {
  producto_cod: string;
  demanda_proxima_semana: number;
}

// ── §1.1 Filtros globales ────────────────────────────────────────────────────
export interface FiltrosBodega {
  almacenes: string[];
  categorias: string[];
  proveedores: string[];
  sucursales: string[];
}

/** Estado de los filtros globales del dashboard (persistido en sesión). */
export interface BodegaFilterState {
  almacen: string | null;
  categoria: string | null;
  proveedor: string | null;
  busqueda: string;
  fechaDesde: string | null; // YYYY-MM-DD
  fechaHasta: string | null;
}

// ── §1.2 KPIs ────────────────────────────────────────────────────────────────
export interface KpisBodega {
  total_articulos: {
    total_skus: number;
    skus_activos: number;
    skus_stock_cero: number;
    cantidad_total: number;
    tendencia_pct: number | null;
  };
  rotacion: {
    rotacion_periodo: number | null;
    rotacion_anualizada: number | null;
    semaforo: 'verde' | 'amarillo' | 'rojo' | 'sin_datos';
  };
  dias_inventario: {
    dias: number | null;
    alerta_desabastecimiento: boolean;
  };
  stock_bajo: {
    productos_bajo_reorden: number;
    pct_del_total: number;
    color: 'verde' | 'amarillo' | 'rojo';
  };
  valor_inventario: {
    valor_total: number;
    tendencia_pct: number | null;
    top_categorias: { categoria: string; valor: number }[];
  };
  tasa_stockout: {
    pct: number | null;
    meta_pct: number;
    alerta: boolean;
  };
}

// ── §1.3 Gráficos ────────────────────────────────────────────────────────────
export interface SalidasForecast {
  producto_cod: string | null;
  metodo: 'ml_demand_rf' | 'estadistico';
  stock_actual: number | null;
  punto_reorden: number | null;
  historial: { fecha: string; unidades: number }[];
  prediccion: { fecha: string; unidades: number; banda_superior: number; banda_inferior: number }[];
}

export interface ProductoRotacion {
  codart: string;
  nombre: string;
  categoria: string;
  rotacion_mensual: number | null;
  margen_unitario: number;
  stock_actual: number;
  valor_inventario: number;
  dias_inventario: number | null;
}

export interface RotacionMatriz {
  productos: ProductoRotacion[];
  mediana_rotacion: number;
  mediana_margen: number;
}

export interface ProductoTopSalidas {
  codart: string;
  nombre: string;
  categoria: string;
  unidades: number;
  stock_actual: number;
  dias_inventario: number | null;
  tendencia_pct: number | null;
}

export interface CategoriaSalidas {
  categoria: string;
  unidades: number;
  unidades_previo: number;
  stock_disponible: number;
  pct_participacion: number;
  tendencia_pct: number | null;
}

export type EstadoStock = 'Crítico' | 'Cerca' | 'Seguro' | 'Exceso';

export interface ProductoStockReorden {
  codart: string;
  nombre: string;
  categoria: string;
  stock_actual: number;
  punto_reorden: number;
  salida_diaria: number;
  dias_inventario: number | null;
  dias_hasta_reorden: number | null;
  estado: EstadoStock;
}

export interface ProductoCompra {
  codart: string;
  nombre: string;
  categoria: string;
  stock_actual: number;
  salida_diaria: number;
  dias_inventario: number | null;
  dias_hasta_reorden: number | null;
  fecha_estimada_reorden: string | null;
  cantidad_sugerida: number;
  costo_unitario: number;
  costo_total: number;
  prioridad?: 'Alta' | 'Media' | 'Baja' | null;
  justificacion?: string | null;
  motivo?: string | null;
}

export interface NecesidadCompra {
  horizonte_dias: number;
  recomendados: Page<ProductoCompra>;
  no_comprar: ProductoCompra[];
  total_productos_a_comprar: number;
  valor_total_compra: number;
  ahorro_por_no_comprar: number;
}

// ── §3 Panel por almacén y transferencias ────────────────────────────────────
export interface ProductoMatrizAlmacen {
  codart: string;
  nombre: string;
  categoria: string;
  stock_por_almacen: Record<string, number>;
  stock_total: number;
  punto_reorden: number;
  dias_inventario: number | null;
  estado: EstadoStock;
}

export interface InventarioMatriz {
  almacenes: string[];
  productos: Page<ProductoMatrizAlmacen>;
}

export interface TransferenciaSugerida {
  codart: string;
  nombre: string;
  categoria: string;
  almacen_origen: string;
  stock_origen: number;
  dias_inv_origen: number | null;
  almacen_destino: string;
  stock_destino: number;
  dias_inv_destino: number | null;
  cantidad_transferir: number;
  dias_inv_destino_post: number | null;
  prioridad: 'Alta' | 'Media' | 'Baja';
  ahorro_estimado: number;
  motivo: string;
}

export interface Transferencias {
  sugerencias: Page<TransferenciaSugerida>;
  total_sugerencias: number;
  ahorro_total_estimado: number;
}

// ── §4 Notificaciones ────────────────────────────────────────────────────────
export interface NotificacionBodega {
  tipo: string;
  prioridad: 'alta' | 'media' | 'baja';
  mensaje: string;
  codart: string | null;
}

// ── §2 Reportes ──────────────────────────────────────────────────────────────
export type TipoReporteBodega = 'justificacion' | 'transferencias' | 'analisis-mensual';

export interface ReporteBodega {
  generado_en: string;
  contenido: Record<string, unknown>;
}

// ── Predicción de compras del próximo mes por categoría (docs/auditoria/24) ──
export interface PuntoPrediccionMes {
  fecha: string;
  unidades: number;
  banda_superior: number;
  banda_inferior: number;
}

export interface ArticuloPrediccionMes {
  codart: string;
  nombre: string;
  categoria: string;
  unidades_vendidas_periodo: number;
  stock_actual: number;
  punto_reorden: number;
  prediccion_mes: number;
  compra_sugerida: number;
  metodo: 'ml_demand_rf' | 'estadistico';
}

export interface PrediccionComprasMes {
  mes_objetivo: string; // "YYYY-MM"
  categoria: string | null;
  producto_cod: string | null;
  metodo: 'ml_demand_rf' | 'estadistico';
  serie: PuntoPrediccionMes[];
  resumen: {
    unidades_previstas_mes: number;
    costo_estimado_compra: number;
    productos_incluidos: number;
  };
  top_articulos: ArticuloPrediccionMes[];
}
