# backend/app/schemas/user.py
from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from datetime import datetime
from app.schemas.role import RoleOut


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

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


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
        if len(v) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres.")
        return v


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
        if v is not None and len(v) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres.")
        return v


class UserChangePassword(BaseModel):
    """Schema para que el usuario autenticado cambie su propia contraseña."""
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("La nueva contraseña debe tener al menos 8 caracteres.")
        return v


# ── Schema heredado (compatibilidad con auth.py) ──────────────────────────────
class UserLogin(BaseModel):
    email: EmailStr
    password: str
