# backend/app/schemas/meta_config.py
"""Esquemas de la configuración editable del motor de metas v2
(docs/features/plan_motor_metas_configurable.md §5.5)."""
import datetime

from pydantic import BaseModel, Field


class MetaConfigParametroOut(BaseModel):
    clave: str
    valor: float
    descripcion: str | None = None
    actualizado_en: datetime.datetime

    class Config:
        from_attributes = True


class MetaConfigParametroUpdate(BaseModel):
    valor: float = Field(gt=0)


class MetaConfigAuditoriaItem(BaseModel):
    usuario: str | None
    accion: str
    detalle: dict
    fecha: datetime.datetime
