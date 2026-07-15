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
