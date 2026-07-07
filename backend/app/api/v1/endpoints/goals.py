# backend/app/api/v1/endpoints/goals.py
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Any
from app.core.deps import SessionDep, CurrentUserDep, PermissionChecker
from app.schemas.goal import GoalReviewPayload, GoalTrackingResponse
from app.services.analytics_service import GoalsAutomationService
from app.models.goal import Goal

router = APIRouter()

# Solo gerencia y administrador pueden usar esto
only_management = PermissionChecker(allowed_roles=["gerencia", "administrador"])

@router.get(
    "/tracking",
    response_model=GoalTrackingResponse,
    summary="Obtiene metas y seguimiento del periodo",
    dependencies=[Depends(only_management)]
)
def get_goals_tracking(anio: int, mes: int, db: SessionDep) -> Any:
    service = GoalsAutomationService(db)
    reporte = service.liquidar_comisiones_periodo(anio=anio, mes=mes)
    return {"reporte_cumplimiento": reporte}

@router.get(
    "/periods",
    status_code=status.HTTP_200_OK,
    summary="Obtiene los periodos disponibles para metas",
    dependencies=[Depends(only_management)]
)
def get_goals_periods(db: SessionDep) -> Any:
    service = GoalsAutomationService(db)
    return service.get_goals_periods()

@router.post(
    "/generate",
    status_code=status.HTTP_200_OK,
    summary="Genera metas automatizadas",
    dependencies=[Depends(only_management)]
)
def generate_goals(anio: int, mes: int, pressure_factor: float, db: SessionDep) -> Any:
    service = GoalsAutomationService(db)
    try:
        creados = service.generar_propuestas_metas(anio=anio, mes=mes, factor_presion=pressure_factor)
        return {"registros_creados": creados, "message": "Generación completada exitosamente"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put(
    "/{goal_id}/review",
    status_code=status.HTTP_200_OK,
    summary="Aprobar o rechazar meta y actualizar comisión",
    dependencies=[Depends(only_management)]
)
def review_goal(
    goal_id: int, 
    payload: GoalReviewPayload, 
    db: SessionDep, 
    current_user: CurrentUserDep
) -> dict:
    goal = db.query(Goal).filter(Goal.id == goal_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Meta no encontrada")
    
    if payload.monto_meta is not None:
        goal.monto_meta = payload.monto_meta
    if payload.comision_base_pct is not None:
        goal.comision_base_pct = payload.comision_base_pct
    
    goal.estado = payload.estado
    goal.approved_by = current_user.id
    
    db.commit()
    return {"message": f"Meta {payload.estado.lower()}"}
