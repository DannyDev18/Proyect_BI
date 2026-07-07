# backend/app/schemas/goal.py
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List

# Esquemas de entrada y validación 
class GoalProposalCreate(BaseModel):
    anio: int = Field(..., ge=2020, description="Año correspondiente a la meta")
    mes: int = Field(..., ge=1, le=12, description="Mes correspondiente")
    id_vendedor_origen: Optional[str] = Field(None, max_length=15)
    sucursal: str = Field(..., min_length=2, max_length=100)
    monto_meta: float = Field(..., ge=0.0)
    unidades_meta: float = Field(..., ge=0.0)

class GoalReviewPayload(BaseModel):
    monto_meta: Optional[float] = Field(None, ge=0.0)
    estado: str = Field(..., pattern="^(APROBADA|RECHAZADA)$")
    comision_base_pct: Optional[float] = Field(None, ge=0.0, le=100.0)

class GoalCommissionReportItem(BaseModel):
    id: int
    vendedor: str
    sucursal: str
    monto_meta: float
    comision_base_pct: float
    estado: str

class GoalTrackingResponse(BaseModel):
    reporte_cumplimiento: List[GoalCommissionReportItem]
