# backend/app/services/user_service.py
import logging

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.security import get_password_hash, verify_password
from app.models.role import Role
from app.models.user import User
from app.repositories.catalog_repository import CatalogRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.user_repository import UserRepository
from app.schemas.pagination import PaginationParams
from app.schemas.user import UserCreate, UserUpdate

logger = logging.getLogger(__name__)

_SIN_CAMBIO = object()  # marca "no se tocaron las bodegas" en update() -- distinto de [] (vaciar)


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
        self, role: Role, id_vendedor_origen: str | None, codalms: list[str], todos_los_almacenes: bool,
    ) -> tuple[str | None, list[str]]:
        """Enlace automático cuenta↔EDW según el rol (panel Administrador):
        - "ventas": exige `id_vendedor_origen` (codven) y lo valida activo en
          edw.Dim_Vendedor -- la cuenta queda enlazada a ese vendedor.
        - "bodega": exige una o varias `codalms` válidas en edw.Dim_Almacen (N:N,
          decisión del usuario 2026-07-29 -- B-2 del plan), salvo que el admin marque
          "todos los almacenes" (`todos_los_almacenes=True`).
        - Otros roles (gerencia, administrador): sin enlace.
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
            return id_vendedor_origen, []

        if role.nombre == "bodega":
            if todos_los_almacenes:
                return None, []
            if not codalms:
                raise ValidationError(
                    "El rol 'bodega' requiere al menos un código de almacén (codalms), "
                    "o marcar 'acceso a todos los almacenes'."
                )
            codalms_dedup = list(dict.fromkeys(codalms))
            for codalm in codalms_dedup:
                if not self.catalog_repo.get_almacen(codalm):
                    raise ValidationError(f"El código de almacén '{codalm}' no existe en el sistema.")
            return None, codalms_dedup

        return None, []

    def get_by_email(self, email: str) -> User | None:
        return self.user_repo.get_by_email(email)

    def get_by_id(self, user_id: int) -> User | None:
        return self.user_repo.get_by_id(user_id)

    def get_all(self, skip: int = 0, limit: int = 100) -> list[User]:
        return self.user_repo.get_all(skip=skip, limit=limit)

    def get_all_paginated(self, pagination: PaginationParams) -> tuple[list[User], int]:
        """Fase 5 §5.1 (docs/features/plan_correcciones_integrales_sistema.md):
        paginación real vía SQL (`OFFSET`/`LIMIT` + `COUNT(*)` ya en `UserRepository`),
        no en memoria. Devuelve `(items, total)` -- el router arma el `Page[UserOut]`
        (no se anota `Page[User]` aquí: `User` es un modelo ORM, no serializable como
        parámetro genérico de un `BaseModel` de Pydantic)."""
        skip = (pagination.page - 1) * pagination.page_size
        items = self.user_repo.get_all(skip=skip, limit=pagination.page_size)
        total = self.user_repo.count()
        return items, total

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
        id_vendedor_origen, codalms = self._resolve_role_link(
            role, user_in.id_vendedor_origen, user_in.codalms, bool(user_in.todos_los_almacenes)
        )

        db_user = self.user_repo.create(
            nombre=user_in.nombre,
            email=user_in.email.lower(),
            hashed_password=get_password_hash(user_in.password),
            rol_id=user_in.rol_id,
            sucursal=user_in.sucursal,
            id_vendedor_origen=id_vendedor_origen,
            todos_los_almacenes=bool(user_in.todos_los_almacenes) if role.nombre == "bodega" else False,
            es_activo=user_in.es_activo if user_in.es_activo is not None else True,
            codalms=codalms,
        )
        return self.user_repo.get_by_id(db_user.id)

    def update(self, db_user: User, user_in: UserUpdate) -> User:
        update_data = user_in.model_dump(exclude_unset=True)
        codalms_in = update_data.pop("codalms", None)  # None = no se tocaron las bodegas

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
        codalms_a_guardar = _SIN_CAMBIO
        if {"rol_id", "id_vendedor_origen", "todos_los_almacenes"} & update_data.keys() or codalms_in is not None:
            id_vendedor_origen = update_data.get("id_vendedor_origen", db_user.id_vendedor_origen)
            codalms = codalms_in if codalms_in is not None else db_user.codalms
            todos_los_almacenes = update_data.get("todos_los_almacenes", db_user.todos_los_almacenes)
            update_data["id_vendedor_origen"], codalms_a_guardar = self._resolve_role_link(
                role, id_vendedor_origen, codalms, bool(todos_los_almacenes)
            )

        if "password" in update_data:
            update_data["hashed_password"] = get_password_hash(update_data.pop("password"))

        extra = {} if codalms_a_guardar is _SIN_CAMBIO else {"codalms": codalms_a_guardar}
        self.user_repo.update(db_user, **extra, **update_data)
        return self.user_repo.get_by_id(db_user.id)

    def change_password(self, db_user: User, current_password: str, new_password: str) -> User:
        if not verify_password(current_password, db_user.hashed_password):
            raise ValidationError("La contraseña actual es incorrecta.")
        return self.user_repo.update(db_user, hashed_password=get_password_hash(new_password))

    def delete_permanente(self, db_user: User, current_user: User) -> None:
        """Fase 5 §5.3 (docs/features/plan_correcciones_integrales_sistema.md): borrado
        duro real, distinto de `deactivate` (baja lógica). Viable porque cada FK hacia
        `public.usuarios` ya declara `ondelete` explícito (`SET NULL` en
        `Goal.approved_by`/`GestionCartera`/`CommissionConfig`/etc., `CASCADE` en
        `notificaciones`/`usuario_almacenes`) -- verificado contra los modelos, ningún
        `RESTRICT` que bloquee el borrado."""
        if db_user.id == current_user.id:
            raise ValidationError("No puedes eliminar tu propia cuenta de administrador.")
        if db_user.role.nombre == "administrador" and db_user.es_activo:
            if self.user_repo.count_administradores_activos() <= 1:
                raise ValidationError(
                    "No se puede eliminar al último administrador activo del sistema."
                )
        self.user_repo.delete(db_user)

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
