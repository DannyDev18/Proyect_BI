# backend/app/services/role_service.py
from sqlalchemy.orm import Session
from app.models.role import Role
from app.schemas.role import RoleCreate


def get_all_roles(db: Session) -> list[Role]:
    """Retorna todos los roles del sistema (4 roles del negocio)."""
    return db.query(Role).order_by(Role.id).all()


def get_role_by_id(db: Session, role_id: int) -> Role | None:
    """Obtiene un rol por su ID."""
    return db.query(Role).filter(Role.id == role_id).first()


def get_role_by_nombre(db: Session, nombre: str) -> Role | None:
    """Obtiene un rol por su nombre (case-insensitive)."""
    return db.query(Role).filter(Role.nombre == nombre.lower()).first()
