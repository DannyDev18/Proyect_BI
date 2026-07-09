# backend/app/api/routes/goals.py
from fastapi import APIRouter, Depends, status

from app.api.dependencies import GoalsServiceDep
from app.core.deps import CurrentUserDep, PermissionChecker
from app.schemas.goal import GoalReviewPayload, GoalTrackingResponse

router = APIRouter()

only_management = PermissionChecker(allowed_roles=["gerencia", "administrador"])


@router.get(
    "/tracking", response_model=GoalTrackingResponse, summary="Obtiene metas y seguimiento del periodo",
    dependencies=[Depends(only_management)],
)
def get_goals_tracking(anio: int, mes: int, goals_service: GoalsServiceDep) -> GoalTrackingResponse:
    reporte = goals_service.get_commission_tracking(anio=anio, mes=mes)
    return GoalTrackingResponse(reporte_cumplimiento=reporte)


@router.get(
    "/periods", status_code=status.HTTP_200_OK, summary="Obtiene los periodos disponibles para metas",
    dependencies=[Depends(only_management)],
)
def get_goals_periods(goals_service: GoalsServiceDep):
    return goals_service.get_periods()


@router.post(
    "/generate", status_code=status.HTTP_200_OK, summary="Genera metas automatizadas",
    dependencies=[Depends(only_management)],
)
def generate_goals(anio: int, mes: int, pressure_factor: float, goals_service: GoalsServiceDep):
    creados = goals_service.generate_proposals(anio=anio, mes=mes, factor_presion=pressure_factor)
    return {"registros_creados": creados, "message": "Generación completada exitosamente"}


@router.put(
    "/{goal_id}/review", status_code=status.HTTP_200_OK, summary="Aprobar o rechazar meta y actualizar comisión",
    dependencies=[Depends(only_management)],
)
def review_goal(
    goal_id: int,
    payload: GoalReviewPayload,
    goals_service: GoalsServiceDep,
    current_user: CurrentUserDep,
) -> dict:
    """Antes accedía al ORM directamente en el router (`db.query(Goal)...db.commit()`);
    ahora delega en `GoalsService.review_goal`, que usa `GoalRepository`."""
    goals_service.review_goal(
        goal_id=goal_id,
        estado=payload.estado,
        approved_by_user_id=current_user.id,
        monto_meta=payload.monto_meta,
        comision_base_pct=payload.comision_base_pct,
    )
    return {"message": f"Meta {payload.estado.lower()}"}
