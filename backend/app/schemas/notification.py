# backend/app/schemas/notification.py
"""Contratos del módulo de Notificaciones (docs/features/plan_modulo_notificaciones.md,
docs/auditoria/31_modulo_notificaciones.md, reglas RN-N1..RN-N4)."""
import datetime
from typing import Optional

from pydantic import BaseModel


class NotificacionOut(BaseModel):
    """Formato unificado devuelto por `GET /notificaciones`, sea la notificación
    calculada al vuelo (id=None, leida=False siempre) o persistida (id real, leida
    según `leida_por` para el usuario del token)."""
    id: Optional[int] = None
    tipo_evento: str
    titulo: str
    mensaje: str
    accion_url: Optional[str] = None
    prioridad: str  # alta | media | baja
    fecha_creacion: Optional[datetime.datetime] = None
    leida: bool = False
    persistida: bool = False


class MarcarLeidaResponse(BaseModel):
    id: int
    leida: bool
