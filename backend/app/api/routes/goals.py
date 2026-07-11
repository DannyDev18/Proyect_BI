# backend/app/api/routes/goals.py
from fastapi import APIRouter, Depends, status

from app.api.dependencies import (
    AnalyticsServiceDep, CommissionServiceDep, GoalMLServiceDep, GoalsServiceDep, resolve_sucursal_filter,
)
from app.core.deps import CurrentUserDep, PermissionChecker
from app.schemas.commission import CommissionTrackingResponse, VendorCommissionRowResponse
from app.schemas.goal import (
    CategoryRecommendationItem, GoalReviewPayload, GoalsAISummaryResponse, GoalTrackingResponse, VendorRiskItem,
)

router = APIRouter()

only_management = PermissionChecker(allowed_roles=["gerencia", "administrador"])
sucursal_gerencia = resolve_sucursal_filter(allow_override=True)


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
def generate_goals(anio: int, mes: int, pressure_factor: float, goal_ml_service: GoalMLServiceDep):
    """Generador OFICIAL de metas (docs/auditoria/19_...md): una fila por vendedor
    (nunca por vendedor×sucursal), usando el motor estadístico IQR sobre Venta Neta
    (`GoalMLService.generate_proposals`), no `goals_rf`."""
    creados = goal_ml_service.generate_proposals(anio=anio, mes=mes, factor_presion=pressure_factor)
    return {"registros_creados": creados, "message": "Generación completada exitosamente"}


@router.get(
    "/ai-summary", response_model=GoalsAISummaryResponse, dependencies=[Depends(only_management)],
    summary="Metas sugeridas por IA, vendedores en riesgo/alta probabilidad, recomendaciones por categoría",
)
def get_goals_ai_summary(
    goal_ml_service: GoalMLServiceDep,
    analytics_service: AnalyticsServiceDep,
    sucursal_filtro: str | None = Depends(sucursal_gerencia),
) -> GoalsAISummaryResponse:
    """Integración ML del módulo Metas y Comisiones (docs/auditoria/15_...): compone
    `ranking_vendedores` real (ventas vs. meta del período vigente) con una
    clasificación de ritmo, y las reglas de recomendación agregadas por categoría."""
    kpis = analytics_service.get_sales_kpis(sucursal=sucursal_filtro)
    clasificacion = goal_ml_service.classify_vendor_risk(kpis["ranking_vendedores"])
    recomendaciones = goal_ml_service.get_category_recommendations()

    en_riesgo = [c for c in clasificacion if c.estado == "en_riesgo"]
    alta_probabilidad = [c for c in clasificacion if c.estado == "alta_probabilidad"]

    return GoalsAISummaryResponse(
        vendedores_en_riesgo=[VendorRiskItem(**c.__dict__) for c in en_riesgo],
        vendedores_alta_probabilidad=[VendorRiskItem(**c.__dict__) for c in alta_probabilidad],
        recomendaciones_por_categoria=[CategoryRecommendationItem(**r.__dict__) for r in recomendaciones],
    )


@router.get(
    "/commissions", response_model=CommissionTrackingResponse, dependencies=[Depends(only_management)],
    summary="Cumplimiento real (Venta Neta) y comisión devengada por vendedor en el período",
)
def get_commissions(anio: int, mes: int, commission_service: CommissionServiceDep) -> CommissionTrackingResponse:
    """Cierra el hallazgo R-1 (`docs/auditoria/14_...md`): `/tracking` solo muestra la
    meta configurada; este endpoint agrega la venta real del período y el tramo de
    comisión resultante (`commission_engine.calcular_comision`)."""
    filas = commission_service.get_commission_tracking(anio=anio, mes=mes)
    return CommissionTrackingResponse(comisiones=[VendorCommissionRowResponse(**f.__dict__) for f in filas])


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
