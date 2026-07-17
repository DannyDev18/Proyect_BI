# backend/app/services/user_service.py
import logging

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.security import get_password_hash, verify_password
from app.models.role import Role
from app.models.user import User
from app.repositories.catalog_repository import CatalogRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserUpdate

logger = logging.getLogger(__name__)


class UserService:
    """Lógica de negocio de usuarios. Depende de los repositorios (acceso a datos),
    nunca de `Session` directamente -- eso mantiene el service testeable con repos
    fake/mock, sin tocar la BD."""

    def __init__(self, user_repo: UserRepository, role_repo: RoleRepository, catalog_repo: CatalogRepository):
        self.user_repo = user_repo
        self.role_repo = role_repo
        self.catalog_repo = catalog_repo

    def _validate_role_exists(self, rol_id: int) -> Role:
        role = self.role_repo.get_by_id(rol_id)
        if not role:
            raise NotFoundError(
                f"El rol con ID {rol_id} no existe. Consulte GET /roles para ver los roles disponibles."
            )
        return role

    def _resolve_role_link(
        self, role: Role, id_vendedor_origen: str | None, codalm: str | None, todos_los_almacenes: bool,
    ) -> tuple[str | None, str | None]:
        """Enlace automático cuenta↔EDW según el rol (panel Administrador):
        - "ventas": exige `id_vendedor_origen` (codven) y lo valida activo en
          edw.Dim_Vendedor -- la cuenta queda enlazada a ese vendedor.
        - "bodega": exige `codalm` válido en edw.Dim_Almacen, salvo que el admin
          marque "todos los almacenes" (`codalm=None`).
        - Otros roles (gerencia, administrador): sin enlace, ambos campos en None.
        """
        if role.nombre == "ventas":
            if not id_vendedor_origen:
                raise ValidationError("El rol 'ventas' requiere un código de vendedor (codven).")
            vendedor = self.catalog_repo.get_vendedor_activo(id_vendedor_origen)
            if not vendedor:
                raise ValidationError(
                    f"El código de vendedor '{id_vendedor_origen}' no existe en el sistema."
                )
            if not vendedor["activo"]:
                raise ValidationError(
                    f"El vendedor '{id_vendedor_origen}' existe pero está inactivo; no se puede enlazar la cuenta."
                )
            return id_vendedor_origen, None

        if role.nombre == "bodega":
            if todos_los_almacenes:
                return None, None
            if not codalm:
                raise ValidationError(
                    "El rol 'bodega' requiere un código de almacén (codalm), o marcar 'acceso a todos los almacenes'."
                )
            almacen = self.catalog_repo.get_almacen(codalm)
            if not almacen:
                raise ValidationError(f"El código de almacén '{codalm}' no existe en el sistema.")
            return None, codalm

        return None, None

    def get_by_email(self, email: str) -> User | None:
        return self.user_repo.get_by_email(email)

    def get_by_id(self, user_id: int) -> User | None:
        return self.user_repo.get_by_id(user_id)

    def get_all(self, skip: int = 0, limit: int = 100) -> list[User]:
        return self.user_repo.get_all(skip=skip, limit=limit)

    def registrar_intento_fallido(self, email: str, ip: str | None) -> None:
        self.user_repo.registrar_intento_fallido(email, ip)

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
        if self.user_repo.get_by_email(user_in.email.lower()):
            raise ConflictError(f"Ya existe un usuario registrado con el correo '{user_in.email}'.")
        if user_in.id_vendedor_origen and self.user_repo.get_by_vendedor(user_in.id_vendedor_origen):
            raise ConflictError(
                f"El código de vendedor '{user_in.id_vendedor_origen}' ya está enlazado a otra cuenta."
            )
        role = self._validate_role_exists(user_in.rol_id)
        id_vendedor_origen, codalm = self._resolve_role_link(
            role, user_in.id_vendedor_origen, user_in.codalm, bool(user_in.todos_los_almacenes)
        )

        db_user = self.user_repo.create(
            nombre=user_in.nombre,
            email=user_in.email.lower(),
            hashed_password=get_password_hash(user_in.password),
            rol_id=user_in.rol_id,
            sucursal=user_in.sucursal,
            id_vendedor_origen=id_vendedor_origen,
            codalm=codalm,
            es_activo=user_in.es_activo if user_in.es_activo is not None else True,
        )
        return self.user_repo.get_by_id(db_user.id)

    def update(self, db_user: User, user_in: UserUpdate) -> User:
        update_data = user_in.model_dump(exclude_unset=True)
        todos_los_almacenes = update_data.pop("todos_los_almacenes", False)

        if "email" in update_data and update_data["email"].lower() != db_user.email.lower():
            update_data["email"] = update_data["email"].lower()
            existente = self.user_repo.get_by_email(update_data["email"])
            if existente and existente.id != db_user.id:
                raise ConflictError(
                    f"Ya existe otro usuario registrado con el correo '{update_data['email']}'."
                )

        if "id_vendedor_origen" in update_data and update_data["id_vendedor_origen"]:
            existente = self.user_repo.get_by_vendedor(update_data["id_vendedor_origen"])
            if existente and existente.id != db_user.id:
                raise ConflictError(
                    f"El código de vendedor '{update_data['id_vendedor_origen']}' ya está "
                    f"enlazado a otra cuenta ('{existente.email}')."
                )

        role = db_user.role
        if "rol_id" in update_data:
            role = self._validate_role_exists(update_data["rol_id"])

        # Solo re-resuelve el enlace rol↔EDW si el cambio toca el rol o los campos
        # de enlace -- evita bloquear ediciones no relacionadas (p.ej. renombrar).
        if {"rol_id", "id_vendedor_origen", "codalm"} & update_data.keys():
            id_vendedor_origen = update_data.get("id_vendedor_origen", db_user.id_vendedor_origen)
            codalm = update_data.get("codalm", db_user.codalm)
            update_data["id_vendedor_origen"], update_data["codalm"] = self._resolve_role_link(
                role, id_vendedor_origen, codalm, bool(todos_los_almacenes)
            )

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
