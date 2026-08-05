# backend/app/schemas/vendor_dashboard.py
"""Dashboard "Mi Negocio" del vendedor (auditoría 43, Fase 5,
docs/auditoria/43_correcciones_sesion_ventas_y_datos.md)."""
from typing import Optional

from pydantic import BaseModel

from app.schemas.cartera360 import ClienteRuta, EfectividadComercialResponse, ProximaAccion


class CuotaVendedor(BaseModel):
    meta_mensual: float
    venta_actual: float
    pct_cumplimiento: float
    nivel: str


class ComisionResumenVendedor(BaseModel):
    """Comisión única y variable (docs/features/plan_motor_metas_v3_y_comisiones_
    unificadas.md, Fase 1, R-1) -- sin esquema plano paralelo ni modo condicionante."""
    comision_devengada: float
    tasa_aplicada_pct: float
    bono_aplicado: float
    dias_restantes_mes: int


class MetaDiariaVendedor(BaseModel):
    # `None` si el vendedor no tiene meta mensual generada todavía.
    objetivo_diario: Optional[float] = None
    venta_hoy: float


class RankingVendedor(BaseModel):
    posicion: int
    total: int


class EvolucionMensualPunto(BaseModel):
    anio: int
    mes: int
    venta_real: float
    meta: float


class ComparativoMesAnterior(BaseModel):
    venta_mes_actual: float
    venta_mes_anterior: float
    variacion_pct: float


class ProductoVendedor(BaseModel):
    codart: str
    nombre: str
    venta: float
    unidades: float


class MiNegocioResponse(BaseModel):
    vendedor_origen: str
    anio: int
    mes: int
    cuota: CuotaVendedor
    comision: ComisionResumenVendedor
    meta_diaria: MetaDiariaVendedor
    # `None` si el código de vendedor no resuelve en `edw.dim_vendedor` (desalineación de
    # datos ya documentada en B-3) -- estado vacío real, nunca una posición inventada.
    ranking: Optional[RankingVendedor] = None
    evolucion_mensual: list[EvolucionMensualPunto]
    comparativo_mes_anterior: Optional[ComparativoMesAnterior] = None
    top_productos: list[ProductoVendedor]
    # Reutiliza `ClienteRuta` de "Mi Ruta Inteligente" -- mismo contrato, sin duplicar
    # tipos ni recalcular churn/segmentación.
    clientes_en_riesgo: list[ClienteRuta]
    pipeline: list[ClienteRuta]
    proximas_acciones: list[ProximaAccion]
    efectividad_comercial: EfectividadComercialResponse
