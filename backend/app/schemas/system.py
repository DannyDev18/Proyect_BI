# backend/app/schemas/system.py
from pydantic import BaseModel


class ProvenanceModelo(BaseModel):
    nombre: str
    algoritmo: str | None = None
    entrenado_en: str | None = None
    activo: bool


class ProvenanceResponse(BaseModel):
    ultima_carga_dw: str | None = None
    modelos: list[ProvenanceModelo]
