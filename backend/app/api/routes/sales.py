# backend/app/api/routes/sales.py
"""Ventas: cumplimiento de metas, riesgo de churn, recomendaciones (cross-selling) y
segmentación de clientes."""
from fastapi import APIRouter, Depends

from app.api.dependencies import AnalyticsServiceDep, GoalMLServiceDep, PredictionServiceDep, resolve_sucursal_filter
from app.core.deps import CurrentUserDep, PermissionChecker
from app.core.exceptions import ValidationError
from app.schemas.analytics import (
    ChurnResponse, ForecastCierreResponse, MetaSugeridaResponse, RecomendacionComercialItem,
    RecomendacionesComercialesResponse, RecomendacionProducto, RecomendacionResponse,
    SegmentacionClienteResponse, VPKPIVentas,
)

router = APIRouter()

vendedor_checker = PermissionChecker(allowed_roles=["administrador", "gerencia", "ventas"])
sucursal_ventas = resolve_sucursal_filter(allow_override=False)


@router.get("/goals", response_model=VPKPIVentas, dependencies=[Depends(vendedor_checker)])
def get_sales_goals(
    analytics_service: AnalyticsServiceDep,
    sucursal_filtro: str | None = Depends(sucursal_ventas),
) -> VPKPIVentas:
    """KPIs de ventas: metas, ranking y proyecciones del período vigente."""
    kpis = analytics_service.get_sales_kpis(sucursal=sucursal_filtro)
    return VPKPIVentas(**kpis)


@router.get("/churn-risk", response_model=ChurnResponse, dependencies=[Depends(vendedor_checker)])
def get_churn_risk_by_client(cliente_id: str, prediction_service: PredictionServiceDep) -> ChurnResponse:
    """Riesgo de abandono de un cliente vía el clasificador entrenado."""
    res = prediction_service.get_churn_risk(cliente_id)
    return ChurnResponse(cliente_id=cliente_id, probabilidad_abandono=res["probabilidad_abandono"], riesgo_alto=res["riesgo_alto"])


@router.get("/recommendations", response_model=RecomendacionResponse, dependencies=[Depends(vendedor_checker)])
def get_recommendations_for_client(cliente_id: str, prediction_service: PredictionServiceDep) -> RecomendacionResponse:
    """Productos que frecuentemente se venden junto con las últimas compras del cliente."""
    res = prediction_service.get_product_recommendations(cliente_id)
    return RecomendacionResponse(
        cliente_id=cliente_id,
        recomendaciones=[RecomendacionProducto(**r) for r in res["recomendaciones"]],
    )


@router.get("/clientes/{cliente_cod}/segmento", response_model=SegmentacionClienteResponse, dependencies=[Depends(vendedor_checker)])
def get_customer_segmentation(cliente_cod: str, prediction_service: PredictionServiceDep) -> SegmentacionClienteResponse:
    """Segmento comercial (RFM + K-Means) de un cliente, calculado al vuelo."""
    res = prediction_service.get_customer_segment(cliente_cod)
    return SegmentacionClienteResponse(cliente_id=cliente_cod, segmento=res["segmento"], nombre_segmento=res["nombre_segmento"])


# ── Integración ML: Metas y Comisiones (docs/auditoria/15_...) — panel del vendedor ──
@router.get(
    "/goals/forecast-cierre", response_model=ForecastCierreResponse, dependencies=[Depends(vendedor_checker)],
    summary="Pronóstico de cierre de mes (modelo de ventas) para la sucursal del usuario",
)
def get_goal_forecast_cierre(
    goal_ml_service: GoalMLServiceDep,
    analytics_service: AnalyticsServiceDep,
    sucursal_filtro: str | None = Depends(sucursal_ventas),
) -> ForecastCierreResponse:
    """% esperado de cumplimiento, ventas proyectadas al cierre y probabilidad de
    alcanzar la meta -- modelo `sales_rf` vía el mismo walk-forward que usa Gerencia,
    horizonte = días restantes del mes en curso."""
    kpis = analytics_service.get_sales_kpis(sucursal=sucursal_filtro)
    resultado = goal_ml_service.forecast_cierre(sucursal=sucursal_filtro, meta_mensual=kpis["meta_mensual"])
    return ForecastCierreResponse(**resultado.__dict__)


@router.get(
    "/goals/meta-sugerida", response_model=MetaSugeridaResponse, dependencies=[Depends(vendedor_checker)],
    summary="Meta sugerida por IA (goals_rf) y por el motor estadístico (IQR + anomalías)",
)
def get_goal_suggestion(goal_ml_service: GoalMLServiceDep, current_user: CurrentUserDep) -> MetaSugeridaResponse:
    if not current_user.id_vendedor_origen:
        raise ValidationError("El usuario actual no tiene un código de vendedor (id_vendedor_origen) asociado.")
    if not current_user.sucursal:
        raise ValidationError("El usuario actual no tiene una sucursal asociada.")
    resultado = goal_ml_service.suggest_goal(current_user.id_vendedor_origen, current_user.sucursal)
    return MetaSugeridaResponse(**resultado.__dict__)


@router.get(
    "/goals/recomendaciones", response_model=RecomendacionesComercialesResponse, dependencies=[Depends(vendedor_checker)],
    summary="Productos recomendados (reglas de asociación) para ayudar a cerrar la meta",
)
def get_goal_recommendations(goal_ml_service: GoalMLServiceDep, current_user: CurrentUserDep) -> RecomendacionesComercialesResponse:
    if not current_user.id_vendedor_origen:
        raise ValidationError("El usuario actual no tiene un código de vendedor (id_vendedor_origen) asociado.")
    recs = goal_ml_service.get_commercial_recommendations(current_user.id_vendedor_origen)
    return RecomendacionesComercialesResponse(
        vendedor_origen=current_user.id_vendedor_origen,
        recomendaciones=[RecomendacionComercialItem(producto_cod=r.producto_cod, score_afinidad=r.score_afinidad) for r in recs],
    )
