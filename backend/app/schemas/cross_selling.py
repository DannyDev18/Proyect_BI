# backend/app/schemas/cross_selling.py
"""Contratos del módulo de Venta Cruzada (docs/auditoria/25_modulo_cross_selling.md,
RN-CS1/RN-CS2). Independientes del esquema interno de `recommendation.pkl`."""
from pydantic import BaseModel, Field


class SugerenciaProducto(BaseModel):
    codart: str
    nombre: str
    precio: float
    categoria: str
    score: float
    motivo: str
    fuente: str  # 'asociacion' | 'popularidad_categoria' | lo que declare el contrato ganador
    # None cuando dim_producto.costo_promedio es NULL/0 (H25-4): no se inventa un costo.
    margen_unitario: float | None = None


class CrossSellSugerenciasRequest(BaseModel):
    items: list[str] = Field(min_length=1)
    cliente_id: str | None = None
    top_n: int | None = None


class CrossSellSugerenciasResponse(BaseModel):
    items: list[str]
    sugerencias: list[SugerenciaProducto]


class CrossSellEventoRequest(BaseModel):
    producto_origen_cod: str
    producto_sugerido_cod: str
    evento: str  # 'mostrada' | 'aceptada' | 'rechazada'
    score_lift: float | None = None
    motivo: str | None = None
    cliente_id: str | None = None


class CrossSellEventoResponse(BaseModel):
    id: int
    evento: str


class ProductoBusqueda(BaseModel):
    codart: str
    nombre: str
    categoria: str
    precio: float
    margen_unitario: float | None = None


class ClienteBusqueda(BaseModel):
    cliente_id: str
    nombre: str


class CrossSellKpisResponse(BaseModel):
    sugerencias_mostradas: int
    sugerencias_aceptadas: int
    sugerencias_rechazadas: int
    tasa_conversion_pct: float


class TopCombinacionProducto(BaseModel):
    """Pareja de productos con mayor co-ocurrencia histórica en facturas válidas
    (docs/auditoria/25_modulo_cross_selling.md §6.4): ejemplo concreto y accionable
    de qué ofrecer, sin depender de telemetría acumulada del asistente."""
    codart_a: str
    nombre_a: str
    codart_b: str
    nombre_b: str
    facturas: int


class TopCombinacionesResponse(BaseModel):
    combinaciones: list[TopCombinacionProducto]
