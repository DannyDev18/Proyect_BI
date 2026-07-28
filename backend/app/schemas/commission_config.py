# backend/app/schemas/commission_config.py
"""Schemas de configuración del sistema de Comisiones Variables (docs/features/
plan_integracion_comisiones_variables.md §3.5)."""
import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ── Matriz de categorías ────────────────────────────────────────────────────────
class MatrizCategoriaResponse(BaseModel):
    id: int
    clase: str
    subclase: Optional[str] = None
    grupo: str
    tasa_pct: float
    base: str
    factor_estrategico: float
    vigente_desde: datetime.date
    vigente_hasta: Optional[datetime.date] = None


class MatrizCategoriaPayload(BaseModel):
    clase: str = Field(..., min_length=1, max_length=5)
    subclase: Optional[str] = Field(None, max_length=5)
    grupo: str = Field(..., pattern="^(A|B|C|S|X)$")
    tasa_pct: float = Field(..., ge=0.0, le=100.0)
    base: str = Field("margen", pattern="^(margen|valor)$")
    factor_estrategico: float = Field(1.0, ge=0.5, le=1.5)


class MatrizCategoriasResponse(BaseModel):
    reglas: List[MatrizCategoriaResponse]


# ── Factores de crédito ─────────────────────────────────────────────────────────
class FactorCreditoResponse(BaseModel):
    id: int
    dias_desde: int
    dias_hasta: Optional[int] = None
    factor: float
    pct_al_facturar: float
    vigente_desde: datetime.date
    vigente_hasta: Optional[datetime.date] = None


class FactorCreditoPayload(BaseModel):
    dias_desde: int = Field(..., ge=0)
    dias_hasta: Optional[int] = Field(None, ge=0)
    factor: float = Field(..., ge=0.0, le=1.5)
    pct_al_facturar: float = Field(100.0, ge=0.0, le=100.0)


class FactoresCreditoPayload(BaseModel):
    factores: List[FactorCreditoPayload]


class FactoresCreditoResponse(BaseModel):
    factores: List[FactorCreditoResponse]


# ── Configuración por vendedor ──────────────────────────────────────────────────
class ConfigVendedorResponse(BaseModel):
    id_vendedor_origen: str
    nombre_vendedor: Optional[str] = None
    tipo: str
    factor_tipo: float
    fecha_ingreso: Optional[datetime.date] = None
    activo: bool


class ConfigVendedorPayload(BaseModel):
    tipo: str = Field(..., pattern="^(externo|interno)$")
    factor_tipo: float = Field(..., ge=0.0, le=1.5)
    fecha_ingreso: Optional[datetime.date] = None


class ConfigVendedoresResponse(BaseModel):
    vendedores: List[ConfigVendedorResponse]


# ── Búsqueda inteligente (autocomplete) ─────────────────────────────────────────
class VendedorBusqueda(BaseModel):
    codven: str
    nombre_vendedor: Optional[str] = None


class ClaseBusqueda(BaseModel):
    clase: str
    productos: int


# ── Proyección de Comisiones Variables (panel "Simulación" de gerencia) ─────────
# Toma los últimos 3 o 6 meses YA CERRADOS como base histórica y proyecta la comisión
# variable del próximo mes calendario -- exclusivamente esquema variable, sin comparar
# contra el plano (ver commission_simulation_service.py::proyectar_comision_variable).
class ProyeccionComisionRequest(BaseModel):
    meses_historico: int = Field(3, description="Ventana de historial a usar como base: 3 o 6 meses.")


class ProyeccionVendedorResponse(BaseModel):
    vendedor_origen: str
    nombre_vendedor: Optional[str] = None
    periodo_proyectado: str
    meses_historico_usados: int
    venta_neta_promedio: float
    margen_bruto_promedio: float
    comision_variable_proyectada: float
    tasa_efectiva_pct: float


class ProyeccionComisionResponse(BaseModel):
    meses_historico: int
    periodo_proyectado: str
    vendedores_proyectados: int
    comision_variable_total_proyectada: float
    margen_bruto_total_promedio: float
    tasa_efectiva_pct_global: float
    detalle: List[ProyeccionVendedorResponse]


# ── Perfil de margen por categoría (Fase 1) ─────────────────────────────────────
class PerfilCategoriaResponse(BaseModel):
    clase: str
    es_servicio: bool
    venta_total: float
    margen_total: float
    margen_pct: float
    num_vendedores: int
    num_lineas: int
    tasa_descuento_prom_pct: float


class PerfilCategoriasResponse(BaseModel):
    perfiles: List[PerfilCategoriaResponse]


# ── Líneas sin costo (salvaguarda 2) ────────────────────────────────────────────
class LineaSinCostoResponse(BaseModel):
    codart: str
    vendedor_origen: str
    venta_afectada: float
    num_lineas: int


class LineasSinCostoResponse(BaseModel):
    lineas: List[LineaSinCostoResponse]


# ── Bitácora de cambios de configuración (Fase 2 ítem 2, plan_actualizacion_modulo_
# metas_comisiones.md §3) ────────────────────────────────────────────────────────
class ComisionConfigAuditoriaResponse(BaseModel):
    id: int
    usuario_id: Optional[int]
    usuario_nombre: Optional[str]
    tabla: str
    accion: str
    detalle_json: dict
    fecha_creacion: datetime.datetime


class ComisionConfigAuditoriaListResponse(BaseModel):
    entradas: List[ComisionConfigAuditoriaResponse]
