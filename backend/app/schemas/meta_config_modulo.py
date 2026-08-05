# backend/app/schemas/meta_config_modulo.py
"""Esquemas de la configuración modular del motor de metas v3 (docs/features/
plan_motor_metas_v3_y_comisiones_unificadas.md §9/§18, Fase 6)."""
import datetime
from typing import Any

from pydantic import BaseModel


class MetaConfigModuloOut(BaseModel):
    etapa: str
    metodo: str | None
    activo: bool
    orden: int
    parametros: dict[str, Any]
    razon_desactivacion: str | None
    actualizado_en: datetime.datetime

    class Config:
        from_attributes = True


class MetaConfigModuloUpdate(BaseModel):
    metodo: str | None = None
    activo: bool
    parametros: dict[str, Any] = {}


class MetaConfigModuloMetodoOut(BaseModel):
    implementado: bool
    descripcion: str
    motivo: str | None = None


class MetaConfigModuloParametroOut(BaseModel):
    """Un parámetro numérico editable de la etapa -- fuente única para que el frontend
    genere un campo de formulario (no un editor de JSON crudo, petición explícita del
    usuario: "estos json se deben construir de forma dinamica en el frontend")."""
    clave: str
    label: str
    tipo: str  # 'int' | 'float'
    min: float
    max: float
    paso: float
    default: float


class MetaConfigModuloCatalogoEtapaOut(BaseModel):
    orden: int
    nombre: str
    metodos: dict[str, MetaConfigModuloMetodoOut]
    parametros: list[MetaConfigModuloParametroOut] = []
