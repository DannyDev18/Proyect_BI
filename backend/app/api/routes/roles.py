# backend/app/api/routes/roles.py
from fastapi import APIRouter, Depends

from app.api.dependencies import RoleServiceDep
from app.core.deps import PermissionChecker
from app.schemas.role import RoleOut

router = APIRouter()

admin_or_gerencia = PermissionChecker(allowed_roles=["administrador", "gerencia"])


@router.get(
    "/", response_model=list[RoleOut], summary="Listar roles disponibles",
    dependencies=[Depends(admin_or_gerencia)],
)
def list_roles(role_service: RoleServiceDep) -> list[RoleOut]:
    """
    Retorna los 4 roles del sistema: `administrador`, `gerencia`, `ventas`, `bodega`.
    **Acceso:** solo `administrador` y `gerencia`.
    """
    return role_service.get_all()
