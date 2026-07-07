# backend/app/api/v1/endpoints/users.py
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List

from app.core.deps import SessionDep, PermissionChecker, CurrentUserDep
from app.schemas.user import UserOut, UserCreate, UserUpdate, UserMe, UserChangePassword
from app.services import user_service
from app.models.user import User

router = APIRouter()
logger = logging.getLogger(__name__)

# ── Dependencias de Roles ─────────────────────────────────────────────────────
only_admin = PermissionChecker(allowed_roles=["administrador"])


# ── Perfil del Usuario Actual (/me) ───────────────────────────────────────────
# IMPORTANTE: Esta ruta DEBE estar definida ANTES de /{user_id}
# para que FastAPI no interprete "me" como un ID numérico.

@router.get(
    "/me",
    response_model=UserMe,
    summary="Perfil del usuario autenticado",
)
def get_my_profile(current_user: CurrentUserDep) -> UserMe:
    """
    Retorna el perfil completo del usuario autenticado.
    
    Incluye el objeto `role` completo (no solo el ID), la `sucursal`
    y el `id_vendedor_origen` para que el frontend configure su vista
    automáticamente según el rol y aplique los filtros de seguridad.
    
    **Acceso:** Cualquier usuario autenticado.
    """
    return current_user


@router.post(
    "/me/change-password",
    status_code=status.HTTP_200_OK,
    summary="Cambiar contraseña propia",
)
def change_my_password(
    passwords: UserChangePassword,
    db: SessionDep,
    current_user: CurrentUserDep,
) -> dict:
    """
    Permite al usuario autenticado cambiar su propia contraseña.
    Requiere la contraseña actual para confirmar identidad.
    
    **Acceso:** Cualquier usuario autenticado.
    """
    user_service.change_user_password(
        db,
        current_user,
        passwords.current_password,
        passwords.new_password,
    )
    return {"message": "Contraseña actualizada correctamente."}


# ── CRUD de Usuarios (Solo Administrador) ─────────────────────────────────────

@router.post(
    "/",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear nuevo usuario",
    dependencies=[Depends(only_admin)],
)
def create_user(
    user_in: UserCreate,
    db: SessionDep,
) -> UserOut:
    """
    Crea un nuevo usuario en la plataforma.
    
    - Requiere un `rol_id` válido (consultar GET /roles/ para ver IDs disponibles).
    - El campo `sucursal` es opcional pero recomendado para roles `ventas` y `bodega`.
    - El `id_vendedor_origen` debe corresponder al `codven` del vendedor en SAP 
      para habilitar filtros analíticos automáticos en el JWT.
    - La contraseña debe tener al menos 8 caracteres.
    
    **Acceso:** Solo `administrador`.
    """
    return user_service.create_new_user(db, user_in)


@router.get(
    "/",
    response_model=List[UserOut],
    summary="Listar todos los usuarios",
    dependencies=[Depends(only_admin)],
)
def list_users(
    db: SessionDep,
    skip: int = 0,
    limit: int = 100,
) -> List[UserOut]:
    """
    Lista todos los usuarios del sistema con su información de rol.
    Soporta paginación con `skip` y `limit`.
    
    **Acceso:** Solo `administrador`.
    """
    return user_service.get_all_users(db, skip=skip, limit=limit)


@router.get(
    "/{user_id}",
    response_model=UserOut,
    summary="Obtener usuario por ID",
    dependencies=[Depends(only_admin)],
)
def get_user(
    user_id: int,
    db: SessionDep,
) -> UserOut:
    """
    Obtiene los datos completos de un usuario por su ID.
    
    **Acceso:** Solo `administrador`.
    """
    user = user_service.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró el usuario con ID {user_id}."
        )
    return user


@router.put(
    "/{user_id}",
    response_model=UserOut,
    summary="Actualizar usuario",
    dependencies=[Depends(only_admin)],
)
def update_user(
    user_id: int,
    user_in: UserUpdate,
    db: SessionDep,
    current_user: CurrentUserDep,
) -> UserOut:
    """
    Actualiza parcialmente un usuario. Solo los campos enviados serán modificados.
    
    - Si se envía `rol_id`, se valida que el rol exista.
    - Si se envía `password`, se hashea automáticamente.
    - Un administrador no puede desactivarse a sí mismo para evitar lockout.
    
    **Acceso:** Solo `administrador`.
    """
    user = user_service.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró el usuario con ID {user_id}."
        )

    # Seguridad: un admin no puede desactivarse a sí mismo
    if user.id == current_user.id and user_in.es_activo is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes desactivar tu propia cuenta de administrador."
        )

    return user_service.update_user(db, user, user_in)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="Desactivar usuario (soft-delete)",
    dependencies=[Depends(only_admin)],
)
def deactivate_user(
    user_id: int,
    db: SessionDep,
    current_user: CurrentUserDep,
) -> dict:
    """
    Desactiva un usuario (soft-delete). El registro se mantiene en la BD 
    para preservar el histórico de auditoría.
    
    Para eliminar permanentemente usa `DELETE /users/{id}/permanent` 
    (no implementado por defecto — requiere confirmación manual).
    
    Un administrador no puede desactivar su propia cuenta.
    
    **Acceso:** Solo `administrador`.
    """
    user = user_service.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró el usuario con ID {user_id}."
        )

    # Seguridad: un admin no puede desactivarse a sí mismo
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes desactivar tu propia cuenta de administrador."
        )

    user_service.deactivate_user(db, user)
    logger.warning(
        f"AUDIT: Administrador '{current_user.email}' desactivó al usuario "
        f"ID={user_id} ({user.email})."
    )
    return {
        "message": f"El usuario '{user.email}' ha sido desactivado exitosamente.",
        "user_id": user_id,
    }


@router.post(
    "/{user_id}/activate",
    response_model=UserOut,
    summary="Reactivar usuario desactivado",
    dependencies=[Depends(only_admin)],
)
def activate_user(
    user_id: int,
    db: SessionDep,
) -> UserOut:
    """
    Re-activa un usuario que fue previamente desactivado.
    
    **Acceso:** Solo `administrador`.
    """
    user = user_service.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró el usuario con ID {user_id}."
        )
    return user_service.activate_user(db, user)
