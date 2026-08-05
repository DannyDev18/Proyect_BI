# backend/app/schemas/replenishment.py
"""Contratos del módulo Reabastecimiento Inteligente (docs/features/plan_reabastecimiento_
inteligente.md). Cada campo derivado de un modelo o de un default declara su procedencia
al lado (`metodo_demanda`, `lead_time_origen`, `metodo_stock_seguridad`) -- regla
transversal del plan: ningún campo se presenta como más confiable de lo que los datos
sostienen."""
import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.schemas.pagination import Page


class ItemReabastecimiento(BaseModel):
    codart: str
    nombre: str
    clase_abc: str
    clase_xyz: str
    stock_actual: float
    costo_unitario: float
    demanda_diaria_media: float
    demanda_diaria_sigma: float
    metodo_demanda: str  # ml_demand_rf | estadistico | sin_historia
    coeficiente_variacion: Optional[float] = None
    lead_time_dias: float
    lead_time_origen: str  # producto | categoria | proveedor | default
    nivel_servicio: float
    z_usado: Optional[float] = None
    stock_seguridad: float
    metodo_stock_seguridad: str  # estocastico | determinista | sin_historia
    punto_reorden: float
    cobertura_dias: Optional[float] = None
    riesgo: str  # critico | alto | medio | bajo | sin_demanda
    cantidad_sugerida: float
    costo_total_sugerido: float
    prioridad_score: int
    razones: List[str]


class ListaReabastecimientoResponse(BaseModel):
    items: Page[ItemReabastecimiento]


class ResumenReabastecimiento(BaseModel):
    total_articulos_evaluados: int
    productos_riesgo_critico: int
    productos_riesgo_alto: int
    productos_con_recomendacion_compra: int
    costo_total_compra_sugerida: float
    cobertura_mediana_dias: Optional[float] = None
    cobertura_promedio_dias: Optional[float] = None


# ── Configuración editable (§6.3) ──────────────────────────────────────────────────
class PoliticaABC(BaseModel):
    clase_abc: str
    nivel_servicio: float

    class Config:
        from_attributes = True


class ActualizarPoliticaRequest(BaseModel):
    nivel_servicio: float


class SimularReabastecimientoRequest(BaseModel):
    almacen: Optional[str] = None
    categoria: Optional[str] = None
    proveedor: Optional[str] = None
    tipo_movimiento: Optional[str] = None
    horizonte_dias: Optional[float] = None
    niveles_servicio: Optional[Dict[str, float]] = None  # {"A": 0.99, "B": 0.95, "C": 0.85}
    lead_time_default_dias: Optional[float] = None


class SimularReabastecimientoResponse(BaseModel):
    resumen_actual: ResumenReabastecimiento
    resumen_simulado: ResumenReabastecimiento
    parametros_simulados: Dict[str, Any]


class AlertaReabastecimiento(BaseModel):
    tipo: str  # cambio_brusco_demanda | tendencia_decreciente
    severidad: str  # media | baja
    codart: str
    nombre: str
    mensaje: str
    accion_url: str


class LeadTimeConfig(BaseModel):
    id: int
    producto: Optional[str] = None
    categoria: Optional[str] = None
    proveedor: Optional[str] = None
    dias: float

    class Config:
        from_attributes = True


class UpsertLeadTimeRequest(BaseModel):
    dias: float
    producto: Optional[str] = None
    categoria: Optional[str] = None
    proveedor: Optional[str] = None


# ── F9 (§6.3/§8, bloque 5 Gestión Operativa): propuestas de compra persistidas ──────
class CrearPropuestaRequest(BaseModel):
    almacen: Optional[str] = None
    categoria: Optional[str] = None
    proveedor: Optional[str] = None
    tipo_movimiento: Optional[str] = None
    horizonte_dias: Optional[float] = None
    solo_criticos: bool = False
    riesgo: Optional[str] = None
    clase_abc: Optional[str] = None
    clase_xyz: Optional[str] = None


class PropuestaCompraLineaOut(BaseModel):
    codart: str
    nombre: str
    cantidad: float
    costo_unitario: float
    costo_total: float
    justificacion: Dict[str, Any]

    class Config:
        from_attributes = True


class PropuestaCompraOut(BaseModel):
    id: int
    estado: str
    usuario_id: Optional[int] = None
    filtros_origen: Dict[str, Any]
    horizonte_dias: float
    total: float
    creado_en: datetime.datetime
    actualizado_en: datetime.datetime

    class Config:
        from_attributes = True


class PropuestaCompraDetalleOut(PropuestaCompraOut):
    lineas: List[PropuestaCompraLineaOut]
