# backend/app/schemas/role.py
from pydantic import BaseModel, ConfigDict
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

    model_config = ConfigDict(from_attributes=True)
