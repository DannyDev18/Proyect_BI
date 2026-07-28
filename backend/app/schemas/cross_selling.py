# backend/app/schemas/cross_selling.py
"""Contratos del módulo de Venta Cruzada (docs/auditoria/25_modulo_cross_selling.md,
RN-CS1/RN-CS2). Independientes del esquema interno de `recommendation.pkl`."""
import datetime

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
    # Fase 5 (docs/features/plan_refactor_venta_cruzada_ia.md): multiplicador REAL ya
    # aplicado al ranking (orden final = score * factor_margen) -- explicabilidad honesta
    # del §2.1 para el caso sin ranker promovido (ver docs/auditoria/40_refactor_venta_cruzada.md).
    factor_margen: float = 1.0


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
    # Campos opcionales (Fase 1, plan_refactor_venta_cruzada_ia.md CAMBIO 1): ausentes
    # (`None`) cuando el cliente no tiene ninguna venta válida en el EDW, nunca 0/vacío
    # inventado -- distingue "sin historial" de "historial en cero".
    ciudad: str | None = None
    ultima_compra: datetime.date | None = None
    frecuencia_12m: int | None = None
    n_compras: int | None = None


class ProductoFavorito(BaseModel):
    codart: str
    nombre: str


class PerfilClienteResponse(BaseModel):
    """Perfil compuesto de un cliente para el asistente de Venta Cruzada (Fase 1):
    compone estadística pura del EDW (Cartera360Repository) con los dos modelos ya
    servidos por cliente (`churn_rf` vía `probabilidad_recompra`, `kmeans_rfm` vía
    `segmento`). Todos los campos numéricos son `None` -- nunca 0 -- cuando el
    cliente no tiene historial suficiente (RN de la Fase 1: estado vacío real, no
    ceros que se leerían como "cliente sin valor")."""
    cliente_id: str
    nombre: str
    ciudad: str | None = None
    tiene_historial: bool
    num_compras: int | None = None
    ultima_compra: datetime.date | None = None
    antiguedad_dias: int | None = None
    valor_historico: float | None = None
    ticket_promedio: float | None = None
    frecuencia_12m: int | None = None
    categoria_favorita: str | None = None
    productos_favoritos: list[ProductoFavorito] = Field(default_factory=list)
    segmento: int | None = None
    nombre_segmento: str | None = None
    # Derivada de churn_rf (§2.2 del plan): probabilidad_recompra = 100 - probabilidad_abandono.
    # No es un modelo aparte -- se documenta así en vez de exponer 3 KPIs que sugieran
    # 3 modelos independientes.
    probabilidad_recompra: float | None = None
    riesgo_alto_abandono: bool | None = None


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


class SimulacionVentaRequest(BaseModel):
    items: list[str] = Field(min_length=1)
    cliente_id: str | None = None


class SimulacionVentaResponse(BaseModel):
    """Fase 3 de docs/features/plan_refactor_venta_cruzada_ia.md (CAMBIO 4/12): cifras
    reales sobre la canasta que el vendedor está armando -- `ticket_estimado` es la
    suma real de `dim_producto.precio_oficial` vigente de los códigos de la canasta,
    NUNCA una predicción. No incluye "probabilidad de cierre de la venta": el EDW no
    tiene ventas perdidas (decisión de negocio confirmada, §2.2 del plan) y el ranker
    de la Fase 2 no fue promovido (docs/auditoria/40_refactor_venta_cruzada.md), así
    que tampoco hay `probabilidad_compra_por_producto` calibrada que mostrar."""
    ticket_estimado: float
    productos_no_encontrados: list[str] = Field(default_factory=list)
    margen_estimado: float | None = None
    incremento_vs_ticket_promedio_cliente: float | None = None
    probabilidad_recompra: float | None = None
    explicacion: str


class ProductoCombo(BaseModel):
    codart: str
    nombre: str
    precio: float
    categoria: str
    margen_unitario: float | None = None


class CombinacionInteligente(BaseModel):
    """Fase 4 (CAMBIO 5/6 del plan): cada combo se genera por una estrategia real y
    declarada (`estrategia`); un combo sin datos suficientes para su estrategia
    simplemente no se emite (nunca se rellena con productos arbitrarios). Los campos
    numéricos que no tienen una base real calculable para esa estrategia quedan `None`
    -- nunca un valor inventado -- y `porque` siempre trae la evidencia real en texto."""
    nombre: str
    estrategia: str
    productos: list[ProductoCombo]
    margen_esperado: float | None = None
    afinidad: float | None = None
    popularidad: float | None = None
    porque: str


class CombosResponse(BaseModel):
    combinaciones: list[CombinacionInteligente]


class FeatureContribucion(BaseModel):
    """Una fila de la explicación SHAP real de `churn_rf` (Fase 6, Opción A: "Explicación
    del modelo", nunca "IA generativa"). `contribucion` positiva empuja hacia mayor
    probabilidad de abandono; negativa, hacia menor."""
    feature: str
    valor: float
    contribucion: float


class ChurnExplicacionResponse(BaseModel):
    cliente_id: str
    contribuciones: list[FeatureContribucion]
