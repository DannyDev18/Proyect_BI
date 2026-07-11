# backend/app/schemas/goal.py
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List

class GoalReviewPayload(BaseModel):
    monto_meta: Optional[float] = Field(None, ge=0.0)
    estado: str = Field(..., pattern="^(APROBADA|RECHAZADA)$")
    comision_base_pct: Optional[float] = Field(None, ge=0.0, le=100.0)

class GoalCommissionReportItem(BaseModel):
    id: int
    vendedor: str
    monto_meta: float
    comision_base_pct: float
    estado: str

class GoalTrackingResponse(BaseModel):
    reporte_cumplimiento: List[GoalCommissionReportItem]

# ── Integración ML: Metas y Comisiones (docs/auditoria/15_...) ──────────────────────
class VendorRiskItem(BaseModel):
    nombre: str
    ventas: float
    meta: float
    pct_cumplimiento: float
    pct_esperado_a_la_fecha: float
    estado: str

class CategoryRecommendationItem(BaseModel):
    categoria_origen: str
    categoria_sugerida: str
    producto_sugerido: str
    score_afinidad: float

class GoalsAISummaryResponse(BaseModel):
    vendedores_en_riesgo: List[VendorRiskItem]
    vendedores_alta_probabilidad: List[VendorRiskItem]
    recomendaciones_por_categoria: List[CategoryRecommendationItem]
