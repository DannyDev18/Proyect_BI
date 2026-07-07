# backend/app/api/v1/endpoints/roles.py
from fastapi import APIRouter, Depends
from typing import List

from app.core.deps import PermissionChecker
from app.schemas.role import RoleOut
from app.services import role_service
from app.core.deps import SessionDep

router = APIRouter()

# Roles visibles para admin y gerencia
admin_or_gerencia = PermissionChecker(allowed_roles=["administrador", "gerencia"])


@router.get(
    "/",
    response_model=List[RoleOut],
    summary="Listar roles disponibles",
    dependencies=[Depends(admin_or_gerencia)],
)
def list_roles(db: SessionDep) -> List[RoleOut]:
    """
    Retorna los 4 roles del sistema.
    
    - **administrador**: Gestión de la plataforma
    - **gerencia**: Acceso total de lectura a KPIs globales
    - **ventas**: Dashboards filtrados por sucursal del vendedor
    - **bodega**: Dashboards de inventario por sucursal
    
    **Acceso:** Solo `administrador` y `gerencia`.
    """
    return role_service.get_all_roles(db)
