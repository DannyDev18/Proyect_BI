# backend/app/schemas/mlops.py
import datetime

from pydantic import BaseModel


class MLOpsStatusResponse(BaseModel):
    is_training: bool
    last_run: str | None
    last_status: str
    logs: list[str]


class ModelStatusResponse(BaseModel):
    name: str
    r2: float | None
    status: str


# ── Fase 3 (docs/features/plan_mejora_pipeline_ml.md §5.1-5.3): gating/promoción ──
class RetrainRequest(BaseModel):
    clave: str = "all"


class PromoteRequest(BaseModel):
    clave: str
    version: str


class ModelRunResponse(BaseModel):
    id: int
    clave: str
    version_candidato: str
    version_campeon_anterior: str | None
    promovido: bool
    metrica_nombre: str | None
    metrica_candidato: float | None
    metrica_campeon_anterior: float | None
    razon: str
    disparado_por: str
    creado_en: datetime.datetime

    model_config = {"from_attributes": True}


class ModelVersionResponse(BaseModel):
    version: str
    metrics: dict[str, float]
    trained_at: str | None = None
    algorithm: str | None = None
    es_campeon_actual: bool = False
