# backend/app/api/routes/users.py
import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import CatalogRepositoryDep, UserServiceDep
from app.core.deps import CurrentUserDep, PermissionChecker
from app.schemas.user import UserChangePassword, UserCreate, UserMe, UserOut, UserUpdate

router = APIRouter()
logger = logging.getLogger(__name__)

only_admin = PermissionChecker(allowed_roles=["administrador"])


@router.get(
    "/catalogos/almacenes", summary="Catálogo de almacenes (edw.Dim_Almacen)",
    dependencies=[Depends(only_admin)],
)
def get_catalogo_almacenes(catalog_repo: CatalogRepositoryDep) -> list[dict]:
    """Lista `codalm` + nombre de los almacenes vigentes, para poblar el selector de
    "almacén" al crear/editar una cuenta con rol `bodega`. **Acceso:** solo `administrador`."""
    return catalog_repo.list_almacenes()


@router.get("/me", response_model=UserMe, summary="Perfil del usuario autenticado")
def get_my_profile(current_user: CurrentUserDep) -> UserMe:
    """Retorna el perfil completo del usuario autenticado. **Acceso:** cualquier usuario autenticado."""
    return current_user


@router.post("/me/change-password", status_code=status.HTTP_200_OK, summary="Cambiar contraseña propia")
def change_my_password(
    passwords: UserChangePassword,
    user_service: UserServiceDep,
    current_user: CurrentUserDep,
) -> dict:
    """Permite al usuario autenticado cambiar su propia contraseña. **Acceso:** cualquier usuario autenticado."""
    user_service.change_password(current_user, passwords.current_password, passwords.new_password)
    return {"message": "Contraseña actualizada correctamente."}


@router.post(
    "/", response_model=UserOut, status_code=status.HTTP_201_CREATED,
    summary="Crear nuevo usuario", dependencies=[Depends(only_admin)],
)
def create_user(user_in: UserCreate, user_service: UserServiceDep) -> UserOut:
    """Crea un nuevo usuario en la plataforma. **Acceso:** solo `administrador`."""
    return user_service.create(user_in)


@router.get(
    "/", response_model=list[UserOut], summary="Listar todos los usuarios",
    dependencies=[Depends(only_admin)],
)
def list_users(user_service: UserServiceDep, skip: int = 0, limit: int = 100) -> list[UserOut]:
    """Lista todos los usuarios del sistema con su información de rol. **Acceso:** solo `administrador`."""
    return user_service.get_all(skip=skip, limit=limit)


@router.get(
    "/{user_id}", response_model=UserOut, summary="Obtener usuario por ID",
    dependencies=[Depends(only_admin)],
)
def get_user(user_id: int, user_service: UserServiceDep) -> UserOut:
    """**Acceso:** solo `administrador`."""
    user = user_service.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No se encontró el usuario con ID {user_id}.")
    return user


@router.put(
    "/{user_id}", response_model=UserOut, summary="Actualizar usuario",
    dependencies=[Depends(only_admin)],
)
def update_user(
    user_id: int, user_in: UserUpdate, user_service: UserServiceDep, current_user: CurrentUserDep,
) -> UserOut:
    """
    Actualiza parcialmente un usuario. Un administrador no puede desactivarse a sí mismo
    para evitar lockout. **Acceso:** solo `administrador`.
    """
    user = user_service.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No se encontró el usuario con ID {user_id}.")
    if user.id == current_user.id and user_in.es_activo is False:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No puedes desactivar tu propia cuenta de administrador.")
    return user_service.update(user, user_in)


@router.delete(
    "/{user_id}", status_code=status.HTTP_200_OK, summary="Desactivar usuario (soft-delete)",
    dependencies=[Depends(only_admin)],
)
def deactivate_user(user_id: int, user_service: UserServiceDep, current_user: CurrentUserDep) -> dict:
    """Desactiva un usuario (soft-delete). Un administrador no puede desactivar su propia cuenta.
    **Acceso:** solo `administrador`."""
    user = user_service.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No se encontró el usuario con ID {user_id}.")
    if user.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No puedes desactivar tu propia cuenta de administrador.")

    user_service.deactivate(user)
    logger.warning(f"AUDIT: Administrador '{current_user.email}' desactivó al usuario ID={user_id} ({user.email}).")
    return {"message": f"El usuario '{user.email}' ha sido desactivado exitosamente.", "user_id": user_id}


@router.post(
    "/{user_id}/activate", response_model=UserOut, summary="Reactivar usuario desactivado",
    dependencies=[Depends(only_admin)],
)
def activate_user(user_id: int, user_service: UserServiceDep) -> UserOut:
    """**Acceso:** solo `administrador`."""
    user = user_service.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No se encontró el usuario con ID {user_id}.")
    return user_service.activate(user)
