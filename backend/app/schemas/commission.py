# backend/app/schemas/commission.py
from pydantic import BaseModel
from typing import Any, List, Optional


class VendorCommissionRowResponse(BaseModel):
    """Comisión única y variable (docs/features/plan_motor_metas_v3_y_comisiones_
    unificadas.md, Fase 1, R-1/R-3): sin el esquema plano paralelo -- `comision_devengada`
    ya es la comisión variable, `componentes` es el desglose de 7 pasos (traza de
    `evaluar_formula`) que el panel expande al hacer clic."""
    id: int
    vendedor: str
    monto_meta: float
    venta_real: float
    pct_cumplimiento: float
    nivel: str
    tasa_aplicada_pct: float
    comision_devengada: float
    estado: str
    componentes: List[dict[str, Any]] = []


class CommissionTrackingResponse(BaseModel):
    comisiones: List[VendorCommissionRowResponse]


class CumplimientoMetaPeriodoResponse(BaseModel):
    """KPI de cumplimiento vs metas del dashboard principal de Gerencia (Fase 2, docs/
    features/plan_correcciones_pendientes.md §3) -- agregado company-wide de metas
    APROBADA del período, sin cálculo de comisión."""
    anio: int
    mes: int
    monto_meta_total: float
    venta_real_total: float
    pct_cumplimiento: float
    vendedores_con_meta_aprobada: int


class MiComisionResponse(BaseModel):
    """Comisión única y variable del vendedor (Fase 1, R-1) -- ya no hay un esquema
    plano paralelo ni un `modo_comision` que condicione si se calcula."""
    vendedor_origen: str
    anio: int
    mes: int
    monto_meta: float
    venta_real: float
    pct_cumplimiento: float
    nivel: str
    tasa_aplicada_pct: float
    bono_aplicado: float
    comision_devengada: float
    dias_restantes_mes: int
    en_alerta_cierre: bool
    mensaje_alerta: Optional[str] = None
    desglose_variable: Optional[dict] = None


class PostGoalInvoiceItemResponse(BaseModel):
    num_factura: str
    fecha: str
    monto_factura: float
    acumulado_venta: float


class PostGoalInvoicesResponse(BaseModel):
    facturas: List[PostGoalInvoiceItemResponse]
