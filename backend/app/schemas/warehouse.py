# backend/app/schemas/warehouse.py
"""Contratos del módulo Bodega (docs/features/modulo_bodega.md, auditoría 23).
Los nombres son únicos y en español — H23-7: no se reutiliza BPKPIBodega (legado)."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.schemas.pagination import Page


# ── §1.1 Filtros globales ─────────────────────────────────────────────────────
class TipoMovimientoOption(BaseModel):
    codigo: str
    etiqueta: str


class FiltrosBodegaResponse(BaseModel):
    almacenes: List[str]
    categorias: List[str]
    proveedores: List[str]
    sucursales: List[str]
    tipos_movimiento: List[TipoMovimientoOption]


# ── §1.2 KPIs ─────────────────────────────────────────────────────────────────
class KpiTotalArticulos(BaseModel):
    total_skus: int
    skus_activos: int
    skus_stock_cero: int
    cantidad_total: float
    tendencia_pct: Optional[float] = None


class KpiRotacion(BaseModel):
    rotacion_periodo: Optional[float] = None
    rotacion_anualizada: Optional[float] = None
    semaforo: str  # verde | amarillo | rojo | sin_datos


class KpiDiasInventario(BaseModel):
    dias: Optional[float] = None
    alerta_desabastecimiento: bool


class KpiStockBajo(BaseModel):
    productos_bajo_reorden: int
    pct_del_total: float
    color: str  # verde | amarillo | rojo


class CategoriaValor(BaseModel):
    categoria: str
    valor: float


class KpiValorInventario(BaseModel):
    valor_total: float
    tendencia_pct: Optional[float] = None
    top_categorias: List[CategoriaValor]


class KpiTasaStockout(BaseModel):
    pct: Optional[float] = None
    meta_pct: float
    alerta: bool


class KpisBodegaResponse(BaseModel):
    total_articulos: KpiTotalArticulos
    rotacion: KpiRotacion
    dias_inventario: KpiDiasInventario
    stock_bajo: KpiStockBajo
    valor_inventario: KpiValorInventario
    tasa_stockout: KpiTasaStockout


# ── §1.3 Gráfico 1: salidas histórico + predicción ────────────────────────────
class PuntoSalidaHistorica(BaseModel):
    fecha: str
    unidades: float


class PuntoSalidaPredicha(BaseModel):
    fecha: str
    unidades: float
    banda_superior: float
    banda_inferior: float


class SalidasForecastResponse(BaseModel):
    producto_cod: Optional[str] = None
    metodo: str  # ml_demand_rf | estadistico
    stock_actual: Optional[float] = None
    punto_reorden: Optional[float] = None
    historial: List[PuntoSalidaHistorica]
    prediccion: List[PuntoSalidaPredicha]


# ── §1.3 Gráfico 2: matriz rotación × margen ─────────────────────────────────
class ProductoRotacion(BaseModel):
    codart: str
    nombre: str
    categoria: str
    rotacion_mensual: Optional[float] = None
    margen_unitario: float
    stock_actual: float
    valor_inventario: float
    dias_inventario: Optional[float] = None


class RotacionMatrizResponse(BaseModel):
    productos: List[ProductoRotacion]
    mediana_rotacion: float
    mediana_margen: float


# ── §1.3 Gráficos 3 y 4 ───────────────────────────────────────────────────────
class ProductoTopSalidas(BaseModel):
    codart: str
    nombre: str
    categoria: str
    unidades: float
    stock_actual: float
    dias_inventario: Optional[float] = None
    tendencia_pct: Optional[float] = None


class CategoriaSalidas(BaseModel):
    categoria: str
    unidades: float
    unidades_previo: float
    stock_disponible: float
    pct_participacion: float
    tendencia_pct: Optional[float] = None


# ── §1.3 Gráfico 5: estado vs punto de reorden ────────────────────────────────
class ProductoStockReorden(BaseModel):
    codart: str
    nombre: str
    categoria: str
    stock_actual: float
    punto_reorden: float
    salida_diaria: float
    dias_inventario: Optional[float] = None
    dias_hasta_reorden: Optional[float] = None
    estado: str  # Crítico | Cerca | Seguro | Exceso


# ── §1.3 Gráfico 6 / §3.3: necesidad de compra ───────────────────────────────
class ProductoCompra(BaseModel):
    codart: str
    nombre: str
    categoria: str
    stock_actual: float
    salida_diaria: float
    dias_inventario: Optional[float] = None
    dias_hasta_reorden: Optional[float] = None
    fecha_estimada_reorden: Optional[str] = None
    cantidad_sugerida: float
    costo_unitario: float
    costo_total: float
    prioridad: Optional[str] = None
    justificacion: Optional[str] = None
    motivo: Optional[str] = None


class NecesidadCompraResponse(BaseModel):
    horizonte_dias: int
    recomendados: Page[ProductoCompra]
    no_comprar: List[ProductoCompra]
    total_productos_a_comprar: int
    valor_total_compra: float
    ahorro_por_no_comprar: float


# ── §3.1 Matriz de inventario por almacén ─────────────────────────────────────
class ProductoMatrizAlmacen(BaseModel):
    codart: str
    nombre: str
    categoria: str
    stock_por_almacen: Dict[str, float]
    stock_total: float
    punto_reorden: float
    dias_inventario: Optional[float] = None
    estado: str


class InventarioMatrizResponse(BaseModel):
    almacenes: List[str]
    productos: Page[ProductoMatrizAlmacen]


# ── §3.2 Transferencias inteligentes ──────────────────────────────────────────
class TransferenciaSugerida(BaseModel):
    codart: str
    nombre: str
    categoria: str
    almacen_origen: str
    stock_origen: float
    dias_inv_origen: Optional[float] = None
    almacen_destino: str
    stock_destino: float
    dias_inv_destino: Optional[float] = None
    cantidad_transferir: float
    dias_inv_destino_post: Optional[float] = None
    prioridad: str
    ahorro_estimado: float
    motivo: str


class TransferenciasResponse(BaseModel):
    sugerencias: Page[TransferenciaSugerida]
    total_sugerencias: int
    ahorro_total_estimado: float


# ── §4 Notificaciones ─────────────────────────────────────────────────────────
class NotificacionBodega(BaseModel):
    tipo: str
    prioridad: str  # alta | media | baja
    mensaje: str
    codart: Optional[str] = None


# ── §2 Reportes (JSON libre: estructuras anidadas grandes y variables) ───────
class ReporteBodegaResponse(BaseModel):
    generado_en: str
    # El contenido depende del tipo de reporte; se expone como dict validado por
    # los servicios (las secciones internas reutilizan los modelos de arriba).
    contenido: Dict[str, Any]


# ── Predicción de compras del próximo mes por categoría (docs/auditoria/24) ──
class PuntoPrediccionMes(BaseModel):
    fecha: str
    unidades: float
    banda_superior: float
    banda_inferior: float


class ResumenPrediccionMes(BaseModel):
    unidades_previstas_mes: float
    costo_estimado_compra: float
    productos_incluidos: int


class ArticuloPrediccionMes(BaseModel):
    codart: str
    nombre: str
    categoria: str
    unidades_vendidas_periodo: float
    stock_actual: float
    punto_reorden: float
    prediccion_mes: float
    compra_sugerida: float
    metodo: str  # ml_demand_rf | estadistico


class PrediccionComprasMesResponse(BaseModel):
    mes_objetivo: str  # "YYYY-MM"
    categoria: Optional[str] = None
    producto_cod: Optional[str] = None
    metodo: str  # ml_demand_rf | estadistico
    serie: List[PuntoPrediccionMes]
    resumen: ResumenPrediccionMes
    top_articulos: List[ArticuloPrediccionMes]
