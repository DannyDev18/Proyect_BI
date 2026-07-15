# backend/app/schemas/cartera360.py
"""Esquemas del módulo Ventas — Cartera de Clientes 360
(docs/features/propuesta_nuevos_modulos_roi.md §4, auditoría 32)."""
from pydantic import BaseModel


class ClienteListaTrabajo(BaseModel):
    cliente_id: str
    nombre_cliente: str
    num_compras: int
    dias_sin_comprar: int
    valor_historico: float
    frecuencia_promedio_dias: float | None
    alerta_caida_frecuencia: bool
    # Churn real del modelo (no la señal estadística de alerta_caida_frecuencia, que solo
    # se usa para armar el shortlist barato -- ver Cartera360Service.get_lista_trabajo).
    probabilidad_abandono: float
    prioridad: float


class ListaTrabajoResponse(BaseModel):
    clientes: list[ClienteListaTrabajo]


class ProductoRecomendadoCliente(BaseModel):
    producto_cod: str
    score: float


class DetalleClienteResponse(BaseModel):
    cliente_id: str
    probabilidad_abandono: float
    riesgo_alto: bool
    segmento: int
    nombre_segmento: str
    productos_recomendados: list[ProductoRecomendadoCliente]


class RegistrarGestionRequest(BaseModel):
    cliente_id: str
    evento: str
    motivo: str | None = None


class RegistrarGestionResponse(BaseModel):
    id: int
    evento: str


class TasaRecuperacionResponse(BaseModel):
    total_gestiones: int
    recompras: int
    tasa_recuperacion_pct: float
