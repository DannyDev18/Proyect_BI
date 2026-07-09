# backend/app/repositories/role_repository.py
from sqlalchemy.orm import Session

from app.models.role import Role
from app.repositories.base import BaseRepository


class RoleRepository(BaseRepository):
    def get_all(self) -> list[Role]:
        return self.db.query(Role).order_by(Role.id).all()

    def get_by_id(self, role_id: int) -> Role | None:
        return self.db.query(Role).filter(Role.id == role_id).first()

    def get_by_nombre(self, nombre: str) -> Role | None:
        return self.db.query(Role).filter(Role.nombre == nombre.lower()).first()
