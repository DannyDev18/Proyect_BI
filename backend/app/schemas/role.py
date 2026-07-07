# backend/app/schemas/role.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class RoleBase(BaseModel):
    nombre: str
    descripcion: Optional[str] = None


class RoleCreate(RoleBase):
    pass


class RoleOut(RoleBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
