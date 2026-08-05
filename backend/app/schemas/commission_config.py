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
    vigente_desde: datetime.date
    vigente_hasta: Optional[datetime.date] = None


class FactorCreditoPayload(BaseModel):
    dias_desde: int = Field(..., ge=0)
    dias_hasta: Optional[int] = Field(None, ge=0)
    factor: float = Field(..., ge=0.0, le=2.0)


class FactoresCreditoPayload(BaseModel):
    factores: List[FactorCreditoPayload]


class FactoresCreditoResponse(BaseModel):
    factores: List[FactorCreditoResponse]


# ── Configuración por vendedor ──────────────────────────────────────────────────
# 'jefe_agencia' (auditoría 44): tercer perfil real de la empresa, con tramos de
# cobranza propios y el componente 'contado_agencia' (requiere `agencia`).
class ConfigVendedorResponse(BaseModel):
    id_vendedor_origen: str
    nombre_vendedor: Optional[str] = None
    tipo: str
    factor_tipo: float
    fecha_ingreso: Optional[datetime.date] = None
    activo: bool
    agencia: Optional[str] = None


class ConfigVendedorPayload(BaseModel):
    tipo: str = Field(..., pattern="^(externo|interno|jefe_agencia)$")
    factor_tipo: float = Field(..., ge=0.0, le=1.5)
    fecha_ingreso: Optional[datetime.date] = None
    agencia: Optional[str] = Field(None, max_length=3, description="Solo aplica a 'jefe_agencia' (establ de su agencia).")


class ConfigVendedoresResponse(BaseModel):
    vendedores: List[ConfigVendedorResponse]


# ── Tramos de comisión sobre COBROS (auditoría 44 §2.1) ─────────────────────────
class TramoCobranzaResponse(BaseModel):
    id: int
    perfil: str
    dias_hasta: Optional[int] = None
    tasa_pct: float
    vigente_desde: datetime.date
    vigente_hasta: Optional[datetime.date] = None


class TramoCobranzaPayload(BaseModel):
    dias_hasta: Optional[int] = Field(None, ge=0, description="Techo del tramo en días de cobro. None = sin tope.")
    tasa_pct: float = Field(..., ge=0.0, le=100.0)


class TramosCobranzaPayload(BaseModel):
    perfil: str = Field(..., pattern="^(externo|interno|jefe_agencia)$")
    tramos: List[TramoCobranzaPayload]


class TramosCobranzaResponse(BaseModel):
    perfil: str
    tramos: List[TramoCobranzaResponse]


class TodosTramosCobranzaResponse(BaseModel):
    """Los 3 perfiles a la vez -- vista completa del panel de configuración."""
    externo: List[TramoCobranzaResponse]
    interno: List[TramoCobranzaResponse]
    jefe_agencia: List[TramoCobranzaResponse]


# ── Tramos de cumplimiento (auditoría 45, docs/features/plan_comisiones_
# sobrecumplimiento_umbral_y_desglose.md) -- multiplicador de
# `multiplicador_cumplimiento` de la fórmula variable. Un solo juego de tramos
# GENÉRICOS (sin diferenciar por perfil, decisión explícita del usuario, §5.3 del
# plan) -- reemplaza los umbrales fijos (90/80/100%) y el escalón plano de
# sobrecumplimiento (1.2x único) por una escala editable desde el panel.
class TramoCumplimientoResponse(BaseModel):
    id: int
    pct_desde: float
    pct_hasta: Optional[float] = None
    multiplicador: float
    etiqueta: str
    bono_fijo: float
    vigente_desde: datetime.date
    vigente_hasta: Optional[datetime.date] = None


class TramoCumplimientoPayload(BaseModel):
    pct_desde: float = Field(..., ge=0.0, description="Cota inferior del tramo, en % de cumplimiento (ej. 90.0).")
    pct_hasta: Optional[float] = Field(None, description="Cota superior del tramo. None = sin tope (último tramo).")
    multiplicador: float = Field(..., ge=0.0, description="Factor aplicado al acumulado de la fórmula en este tramo.")
    etiqueta: str = Field(..., min_length=1, max_length=50)
    bono_fijo: float = Field(0.0, ge=0.0, description="Monto fijo en $ que se suma a los bonos al alcanzar el tramo.")


class TramosCumplimientoPayload(BaseModel):
    tramos: List[TramoCumplimientoPayload]


# ── Fórmula de comisión (auditoría 44 §2.2: estructura editable, no quemada) ────
class FormulaComponenteResponse(BaseModel):
    id: int
    orden: int
    componente: str
    operador: str
    activo: bool
    parametros: dict


class FormulaResponse(BaseModel):
    id: int
    clave: str
    nombre: str
    activa: bool
    componentes: List[FormulaComponenteResponse]


class FormulasResponse(BaseModel):
    formulas: List[FormulaResponse]
    catalogo_componentes: List[str] = Field(
        ..., description="Claves de componente válidas -- el editor del frontend solo permite elegir de esta lista.",
    )


class FormulaComponentePayload(BaseModel):
    orden: int = Field(..., ge=1)
    componente: str
    operador: str = Field(..., pattern="^(sumar|restar|multiplicar)$")
    activo: bool = True
    parametros: dict = Field(default_factory=dict)


class FormulaComponentesPayload(BaseModel):
    componentes: List[FormulaComponentePayload]


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
    """Dos modos mutuamente excluyentes: `meses_historico` proyecta el PRÓXIMO mes
    calendario promediando 3 o 6 meses ya cerrados (cumplimiento neutro, sin meta
    todavía); `anio`+`mes` reconstruye la comisión REAL que se hubiera pagado en ESE
    mes específico ya cerrado, con la configuración de comisión variable vigente hoy
    y la meta/bonos/devoluciones reales de ese período."""
    meses_historico: Optional[int] = Field(None, description="Ventana de historial para proyectar el próximo mes: 3 o 6. No usar junto con anio/mes.")
    anio: Optional[int] = Field(None, description="Año del mes específico a reconstruir. Requiere `mes`.")
    mes: Optional[int] = Field(None, ge=1, le=12, description="Mes específico a reconstruir (1-12). Requiere `anio`.")
    # Fase 4 (docs/features/plan_motor_metas_v3_y_comisiones_unificadas.md, R-4): solo
    # aplica junto con anio/mes. `True` (default, compatibilidad) = "qué se hubiera
    # pagado con la config de HOY"; `False` = "reconstrucción fiel" con la config
    # vigente al cierre de ese período, la que debe coincidir con lo que realmente se
    # liquidó/liquidaría.
    usar_configuracion_de_hoy: bool = Field(
        True, description="Solo con anio/mes: True = config vigente hoy, False = reconstrucción fiel con la config vigente al cierre del período.",
    )


class ComponenteComisionResponse(BaseModel):
    """Un paso de la tubería de la fórmula, con etiqueta legible -- auditoría 45
    (docs/features/plan_comisiones_sobrecumplimiento_umbral_y_desglose.md §3.3): "cómo
    se construye la comisión, cuánto gané de cada cosa". `monto` es dinero ($) para
    `sumar`/`restar`; para `multiplicar` es un FACTOR adimensional (`es_factor=True`,
    el frontend no debe formatearlo como moneda)."""
    orden: int
    componente: str
    etiqueta: str
    operador: str
    monto: float
    es_factor: bool
    acumulado_tras_paso: float


class ProyeccionVendedorResponse(BaseModel):
    vendedor_origen: str
    nombre_vendedor: Optional[str] = None
    periodo_proyectado: str
    meses_historico_usados: int
    venta_neta_promedio: float
    margen_bruto_promedio: float
    comision_variable_proyectada: float
    tasa_efectiva_pct: float
    pct_cumplimiento: Optional[float] = None
    nivel: Optional[str] = None
    multiplicador_cumplimiento: float = 1.0
    comisiona: bool = True
    componentes: List[ComponenteComisionResponse] = Field(default_factory=list)


class ProyeccionComisionResponse(BaseModel):
    meses_historico: int
    periodo_proyectado: str
    vendedores_proyectados: int
    comision_variable_total_proyectada: float
    margen_bruto_total_promedio: float
    tasa_efectiva_pct_global: float
    detalle: List[ProyeccionVendedorResponse]
    # Fase 4 (R-4): "reconstruccion_fiel" (config al cierre, coincide con lo real) |
    # "config_actual" (config de hoy sobre un mes pasado, un "qué pasaría si") |
    # "proyeccion" (mes futuro, sin bonos/devoluciones -- eventos puntuales del mes
    # cerrado, no proyectables).
    modo: str = "proyeccion"


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
