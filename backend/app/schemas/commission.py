# backend/app/schemas/commission.py
from pydantic import BaseModel
from typing import List, Optional


class VendorCommissionRowResponse(BaseModel):
    id: int
    vendedor: str
    monto_meta: float
    venta_real: float
    pct_cumplimiento: float
    nivel: str
    tasa_aplicada_pct: float
    comision_devengada: float
    estado: str
    comision_variable: Optional[float] = None
    nivel_variable: Optional[str] = None


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
    comision_variable: Optional[float] = None
    nivel_variable: Optional[str] = None
    desglose_variable: Optional[dict] = None


class PostGoalInvoiceItemResponse(BaseModel):
    num_factura: str
    fecha: str
    monto_factura: float
    acumulado_venta: float


class PostGoalInvoicesResponse(BaseModel):
    facturas: List[PostGoalInvoiceItemResponse]
