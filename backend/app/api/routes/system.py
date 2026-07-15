# backend/app/api/routes/system.py
"""Procedencia de datos visible en cada página autenticada (`ProvenanceRail` del
frontend, docs/auditoria/33_actualizacion_modulo_gerencia.md, H4). Sin restricción de
rol: la misma barra se muestra a los 4 roles, así que el endpoint solo exige un
usuario autenticado, no un permiso de negocio específico."""
from fastapi import APIRouter

from app.api.dependencies import SystemServiceDep
from app.core.deps import CurrentUserDep
from app.schemas.system import ProvenanceResponse

router = APIRouter()


@router.get("/provenance", response_model=ProvenanceResponse)
def get_provenance(_current_user: CurrentUserDep, system_service: SystemServiceDep) -> ProvenanceResponse:
    """Última carga exitosa del DW (`edw.etl_control`) + algoritmo/frescura/estado de
    los 6 modelos ML servidos. Reemplaza el mock estático `PROVENANCE_FACTS`."""
    return ProvenanceResponse(**system_service.get_provenance())
