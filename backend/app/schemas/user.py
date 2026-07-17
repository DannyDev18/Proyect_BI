# backend/app/schemas/user.py
import re

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator
from typing import Optional
from datetime import datetime
from app.core.config import settings
from app.schemas.role import RoleOut


def _validar_politica_password(v: str) -> str:
    """Política única de contraseña (docs/auditoria/36_actualizacion_modulo_admin.md,
    H4): antes solo se validaba en el frontend vía `pattern` HTML, evadible con un
    request directo a la API. `PASSWORD_MIN_LENGTH`/`PASSWORD_REGEX` en
    `core/config.py` son la fuente de verdad; el pattern del frontend queda como UX."""
    if len(v) < settings.PASSWORD_MIN_LENGTH:
        raise ValueError(f"La contraseña debe tener al menos {settings.PASSWORD_MIN_LENGTH} caracteres.")
    if not re.match(settings.PASSWORD_REGEX, v):
        raise ValueError(
            "La contraseña debe incluir al menos una mayúscula, una minúscula, "
            "un número y un carácter especial (@$!%*?&)."
        )
    return v


# ── Schemas de salida (response) ──────────────────────────────────────────────

class UserOut(BaseModel):
    """Schema de respuesta completo para el admin (CRUD de usuarios)."""
    id: int
    nombre: str
    email: EmailStr
    sucursal: Optional[str] = None
    id_vendedor_origen: Optional[str] = None
    codalm: Optional[str] = None
    es_activo: bool
    created_at: datetime
    updated_at: datetime
    role: RoleOut  # Objeto completo del rol (no solo el ID)

    model_config = ConfigDict(from_attributes=True)


class UserMe(BaseModel):
    """
    Schema del perfil del usuario autenticado actual.
    Retornado por GET /users/me — usado por el frontend para configurar su vista.
    """
    id: int
    nombre: str
    email: EmailStr
    sucursal: Optional[str] = None
    id_vendedor_origen: Optional[str] = None
    codalm: Optional[str] = None
    es_activo: bool
    role: RoleOut

    model_config = ConfigDict(from_attributes=True)


# ── Schemas de entrada (request) ──────────────────────────────────────────────

class UserCreate(BaseModel):
    """Schema para crear un nuevo usuario. Solo el administrador puede usarlo.

    Enlace automático por rol (UserService._validate_role_link):
    - rol "ventas": `id_vendedor_origen` (codven) es obligatorio y se valida contra
      edw.Dim_Vendedor -- debe existir y estar `activo`.
    - rol "bodega": `codalm` es obligatorio y se valida contra edw.Dim_Almacen,
      salvo que `todos_los_almacenes=True` (acceso a todos los almacenes, `codalm=NULL`).
    """
    nombre: str
    email: EmailStr
    password: str
    rol_id: int
    sucursal: Optional[str] = None
    id_vendedor_origen: Optional[str] = None
    codalm: Optional[str] = None
    todos_los_almacenes: Optional[bool] = False
    es_activo: Optional[bool] = True

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        return _validar_politica_password(v)


class UserUpdate(BaseModel):
    """Schema para actualizar un usuario (todos los campos son opcionales)."""
    nombre: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    rol_id: Optional[int] = None
    sucursal: Optional[str] = None
    id_vendedor_origen: Optional[str] = None
    codalm: Optional[str] = None
    todos_los_almacenes: Optional[bool] = None
    es_activo: Optional[bool] = None

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str | None) -> str | None:
        return _validar_politica_password(v) if v is not None else v


class UserChangePassword(BaseModel):
    """Schema para que el usuario autenticado cambie su propia contraseña."""
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        return _validar_politica_password(v)


# ── Schema heredado (compatibilidad con auth.py) ──────────────────────────────
class UserLogin(BaseModel):
    email: EmailStr
    password: str
