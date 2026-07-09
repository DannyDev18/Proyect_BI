# backend/app/services/role_service.py
from app.models.role import Role
from app.repositories.role_repository import RoleRepository


class RoleService:
    def __init__(self, role_repo: RoleRepository):
        self.role_repo = role_repo

    def get_all(self) -> list[Role]:
        """Retorna todos los roles del sistema (4 roles del negocio)."""
        return self.role_repo.get_all()
