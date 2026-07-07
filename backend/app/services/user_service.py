# backend/app/services/user_service.py
import logging
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, status

from app.models.user import User
from app.models.role import Role
from app.schemas.user import UserCreate, UserUpdate
from app.core.security import get_password_hash, verify_password

logger = logging.getLogger(__name__)


# ── Helpers internos ──────────────────────────────────────────────────────────

def _validate_role_exists(db: Session, rol_id: int) -> Role:
    """Valida que el rol_id exista en la BD. Eleva 404 si no."""
    role = db.query(Role).filter(Role.id == rol_id).first()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"El rol con ID {rol_id} no existe. Consulte GET /roles para ver los roles disponibles."
        )
    return role


def _query_users_with_role(db: Session):
    """Query base con joinedload del rol para evitar N+1 queries."""
    return db.query(User).options(joinedload(User.role))


# ── Consultas ─────────────────────────────────────────────────────────────────

def get_user_by_email(db: Session, email: str) -> User | None:
    """Obtiene un usuario por email (con rol cargado)."""
    return (
        _query_users_with_role(db)
        .filter(User.email == email)
        .first()
    )


def get_user_by_id(db: Session, user_id: int) -> User | None:
    """Obtiene un usuario por ID (con rol cargado)."""
    return (
        _query_users_with_role(db)
        .filter(User.id == user_id)
        .first()
    )


def get_all_users(db: Session, skip: int = 0, limit: int = 100) -> list[User]:
    """Lista todos los usuarios con su rol, paginados. Solo para administradores."""
    return (
        _query_users_with_role(db)
        .order_by(User.id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def count_users(db: Session) -> int:
    """Cuenta el total de usuarios (para paginación en el frontend)."""
    return db.query(User).count()


# ── Autenticación ─────────────────────────────────────────────────────────────

def authenticate_user(db: Session, email: str, password: str) -> User | None:
    """
    Valida credenciales de email y contraseña.
    Retorna None si las credenciales son incorrectas (sin revelar cuál).
    """
    user = get_user_by_email(db, email)
    if not user:
        # Tiempo constante para evitar user-enumeration via timing attack
        get_password_hash("dummy_to_prevent_timing_attack")
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


# ── Mutaciones (solo admins) ──────────────────────────────────────────────────

def create_new_user(db: Session, user_in: UserCreate) -> User:
    """
    Crea un nuevo usuario en public.usuarios.
    Valida que no exista el email y que el rol_id sea válido.
    """
    # Validar que el email no exista
    existing = get_user_by_email(db, user_in.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un usuario registrado con el correo '{user_in.email}'."
        )

    # Validar que el rol exista
    _validate_role_exists(db, user_in.rol_id)

    db_user = User(
        nombre=user_in.nombre,
        email=user_in.email.lower(),
        hashed_password=get_password_hash(user_in.password),
        rol_id=user_in.rol_id,
        sucursal=user_in.sucursal,
        id_vendedor_origen=user_in.id_vendedor_origen,
        es_activo=user_in.es_activo if user_in.es_activo is not None else True,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    # Recargar con la relación del rol para el response
    return get_user_by_id(db, db_user.id)


def update_user(db: Session, db_user: User, user_in: UserUpdate) -> User:
    """
    Actualiza parcialmente un usuario. Solo se modifican los campos enviados.
    Si se envía rol_id, valida que exista.
    """
    update_data = user_in.model_dump(exclude_unset=True)

    if "rol_id" in update_data:
        _validate_role_exists(db, update_data["rol_id"])

    for field, value in update_data.items():
        if field == "password":
            db_user.hashed_password = get_password_hash(value)
        elif field != "password":
            setattr(db_user, field, value)

    db.commit()
    db.refresh(db_user)
    return get_user_by_id(db, db_user.id)


def change_user_password(db: Session, db_user: User, current_password: str, new_password: str) -> User:
    """
    Permite al usuario autenticado cambiar su propia contraseña.
    Valida la contraseña actual antes de actualizar.
    """
    if not verify_password(current_password, db_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña actual es incorrecta."
        )
    db_user.hashed_password = get_password_hash(new_password)
    db.commit()
    db.refresh(db_user)
    return db_user


def deactivate_user(db: Session, db_user: User) -> User:
    """
    Desactiva un usuario (soft-delete). El registro se mantiene en BD
    para preservar integridad referencial e histórico de auditoría.
    """
    if not db_user.es_activo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El usuario ya se encuentra desactivado."
        )
    db_user.es_activo = False
    db.commit()
    db.refresh(db_user)
    logger.info(f"AUDIT: Usuario ID={db_user.id} ({db_user.email}) desactivado.")
    return db_user


def activate_user(db: Session, db_user: User) -> User:
    """Re-activa un usuario previamente desactivado."""
    if db_user.es_activo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El usuario ya se encuentra activo."
        )
    db_user.es_activo = True
    db.commit()
    db.refresh(db_user)
    logger.info(f"AUDIT: Usuario ID={db_user.id} ({db_user.email}) reactivado.")
    return db_user


def delete_user_permanently(db: Session, db_user: User) -> None:
    """
    Elimina permanentemente un usuario (hard-delete).
    ADVERTENCIA: No puede eliminarse el último usuario administrador.
    """
    # Guardar email para el log antes de eliminar
    email = db_user.email
    user_id = db_user.id
    db.delete(db_user)
    db.commit()
    logger.warning(f"AUDIT: Usuario ID={user_id} ({email}) eliminado permanentemente.")
