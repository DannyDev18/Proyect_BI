# backend/app/services/user_service.py
import logging

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.security import get_password_hash, verify_password
from app.models.user import User
from app.repositories.role_repository import RoleRepository
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserUpdate

logger = logging.getLogger(__name__)


class UserService:
    """Lógica de negocio de usuarios. Depende de los repositorios (acceso a datos),
    nunca de `Session` directamente -- eso mantiene el service testeable con repos
    fake/mock, sin tocar la BD."""

    def __init__(self, user_repo: UserRepository, role_repo: RoleRepository):
        self.user_repo = user_repo
        self.role_repo = role_repo

    def _validate_role_exists(self, rol_id: int) -> None:
        if not self.role_repo.get_by_id(rol_id):
            raise NotFoundError(
                f"El rol con ID {rol_id} no existe. Consulte GET /roles para ver los roles disponibles."
            )

    def get_by_email(self, email: str) -> User | None:
        return self.user_repo.get_by_email(email)

    def get_by_id(self, user_id: int) -> User | None:
        return self.user_repo.get_by_id(user_id)

    def get_all(self, skip: int = 0, limit: int = 100) -> list[User]:
        return self.user_repo.get_all(skip=skip, limit=limit)

    def authenticate(self, email: str, password: str) -> User | None:
        """Valida credenciales. Retorna None si son incorrectas (sin revelar cuál)."""
        user = self.user_repo.get_by_email(email)
        if not user:
            # Tiempo constante para evitar user-enumeration via timing attack
            get_password_hash("dummy_to_prevent_timing_attack")
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    def create(self, user_in: UserCreate) -> User:
        if self.user_repo.get_by_email(user_in.email):
            raise ConflictError(f"Ya existe un usuario registrado con el correo '{user_in.email}'.")
        self._validate_role_exists(user_in.rol_id)

        db_user = self.user_repo.create(
            nombre=user_in.nombre,
            email=user_in.email.lower(),
            hashed_password=get_password_hash(user_in.password),
            rol_id=user_in.rol_id,
            sucursal=user_in.sucursal,
            id_vendedor_origen=user_in.id_vendedor_origen,
            es_activo=user_in.es_activo if user_in.es_activo is not None else True,
        )
        return self.user_repo.get_by_id(db_user.id)

    def update(self, db_user: User, user_in: UserUpdate) -> User:
        update_data = user_in.model_dump(exclude_unset=True)

        if "rol_id" in update_data:
            self._validate_role_exists(update_data["rol_id"])

        if "password" in update_data:
            update_data["hashed_password"] = get_password_hash(update_data.pop("password"))

        self.user_repo.update(db_user, **update_data)
        return self.user_repo.get_by_id(db_user.id)

    def change_password(self, db_user: User, current_password: str, new_password: str) -> User:
        if not verify_password(current_password, db_user.hashed_password):
            raise ValidationError("La contraseña actual es incorrecta.")
        return self.user_repo.update(db_user, hashed_password=get_password_hash(new_password))

    def deactivate(self, db_user: User) -> User:
        if not db_user.es_activo:
            raise ValidationError("El usuario ya se encuentra desactivado.")
        result = self.user_repo.update(db_user, es_activo=False)
        logger.info(f"AUDIT: Usuario ID={db_user.id} ({db_user.email}) desactivado.")
        return result

    def activate(self, db_user: User) -> User:
        if db_user.es_activo:
            raise ValidationError("El usuario ya se encuentra activo.")
        result = self.user_repo.update(db_user, es_activo=True)
        logger.info(f"AUDIT: Usuario ID={db_user.id} ({db_user.email}) reactivado.")
        return result

    def delete_permanently(self, db_user: User) -> None:
        email, user_id = db_user.email, db_user.id
        self.user_repo.delete(db_user)
        logger.warning(f"AUDIT: Usuario ID={user_id} ({email}) eliminado permanentemente.")
