# backend/app/api/routes/sales.py
"""Ventas: cumplimiento de metas, riesgo de churn, recomendaciones (cross-selling) y
segmentación de clientes."""
import datetime

from fastapi import APIRouter, Depends

from app.api.dependencies import (
    AnalyticsServiceDep, CommissionServiceDep, GoalMLServiceDep, PredictionServiceDep, resolve_sucursal_filter,
)
from app.core.deps import CurrentUserDep, PermissionChecker
from app.core.exceptions import ValidationError
from app.schemas.analytics import (
    ChurnResponse, ForecastCierreResponse, MetaSugeridaResponse, RecomendacionComercialItem,
    RecomendacionesComercialesResponse, RecomendacionProducto, RecomendacionResponse,
    SegmentacionClienteResponse, VPKPIVentas,
)
from app.schemas.commission import MiComisionResponse, PostGoalInvoiceItemResponse, PostGoalInvoicesResponse
from app.schemas.cross_selling import (
    ClienteBusqueda, CrossSellEventoRequest, CrossSellEventoResponse, CrossSellKpisResponse,
    CrossSellSugerenciasRequest, CrossSellSugerenciasResponse, ProductoBusqueda, SugerenciaProducto,
    TopCombinacionProducto, TopCombinacionesResponse,
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
    summary="Meta sugerida por el motor estadístico (IQR + anomalías, sin ML)",
)
def get_goal_suggestion(goal_ml_service: GoalMLServiceDep, current_user: CurrentUserDep) -> MetaSugeridaResponse:
    if not current_user.id_vendedor_origen:
        raise ValidationError("El usuario actual no tiene un código de vendedor (id_vendedor_origen) asociado.")
    resultado = goal_ml_service.suggest_goal(current_user.id_vendedor_origen)
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


def _requerir_vendedor(current_user: CurrentUserDep) -> str:
    if not current_user.id_vendedor_origen:
        raise ValidationError("El usuario actual no tiene un código de vendedor (id_vendedor_origen) asociado.")
    return current_user.id_vendedor_origen


@router.get(
    "/goals/mi-comision", response_model=MiComisionResponse, dependencies=[Depends(vendedor_checker)],
    summary="Cumplimiento real (Venta Neta) y comisión devengada del mes en curso, para el vendedor autenticado",
)
def get_my_commission(commission_service: CommissionServiceDep, current_user: CurrentUserDep) -> MiComisionResponse:
    """Panel del vendedor (docs/modulo_metas.md): progreso, tramo de comisión y
    alerta de última semana si va por debajo del 70%. Filtrado por
    `current_user.id_vendedor_origen` -- no existe un rol `vendedor` individual en el
    catálogo cerrado de roles (docs/auditoria/14_...md §4, camino más barato elegido)."""
    vendedor_origen = _requerir_vendedor(current_user)
    hoy = datetime.date.today()
    resultado = commission_service.get_my_commission(vendedor_origen, hoy.year, hoy.month)
    return MiComisionResponse(**resultado.__dict__)


@router.get(
    "/goals/facturas-post-meta", response_model=PostGoalInvoicesResponse, dependencies=[Depends(vendedor_checker)],
    summary="Facturas emitidas después de alcanzar el 100% de la meta del mes en curso",
)
def get_post_goal_invoices(commission_service: CommissionServiceDep, current_user: CurrentUserDep) -> PostGoalInvoicesResponse:
    vendedor_origen = _requerir_vendedor(current_user)
    hoy = datetime.date.today()
    facturas = commission_service.get_post_goal_invoices(vendedor_origen, hoy.year, hoy.month)
    return PostGoalInvoicesResponse(facturas=[PostGoalInvoiceItemResponse(**f.__dict__) for f in facturas])


# ── Asistente de Venta Cruzada (docs/auditoria/25_modulo_cross_selling.md) ──────────
@router.post(
    "/cross-selling/sugerencias", response_model=CrossSellSugerenciasResponse, dependencies=[Depends(vendedor_checker)],
    summary="Sugerencias de venta cruzada para una canasta simulada",
)
def get_cross_sell_sugerencias(
    body: CrossSellSugerenciasRequest, prediction_service: PredictionServiceDep,
) -> CrossSellSugerenciasResponse:
    sugerencias = prediction_service.get_basket_recommendations(body.items, body.cliente_id, body.top_n)
    return CrossSellSugerenciasResponse(items=body.items, sugerencias=[SugerenciaProducto(**s) for s in sugerencias])


@router.post(
    "/cross-selling/eventos", response_model=CrossSellEventoResponse, dependencies=[Depends(vendedor_checker)],
    summary="Registra un evento de telemetría (mostrada/aceptada/rechazada) de una sugerencia",
)
def post_cross_sell_evento(
    body: CrossSellEventoRequest, prediction_service: PredictionServiceDep, current_user: CurrentUserDep,
) -> CrossSellEventoResponse:
    event_id = prediction_service.log_recommendation_event(
        usuario_id=current_user.id,
        producto_origen_cod=body.producto_origen_cod,
        producto_sugerido_cod=body.producto_sugerido_cod,
        evento=body.evento,
        score_lift=body.score_lift,
        motivo=body.motivo,
        cliente_id=body.cliente_id,
    )
    return CrossSellEventoResponse(id=event_id or 0, evento=body.evento)


@router.get(
    "/cross-selling/kpis", response_model=CrossSellKpisResponse, dependencies=[Depends(vendedor_checker)],
    summary="Tasa de conversión del módulo de Venta Cruzada (RN-CS2)",
)
def get_cross_sell_kpis(
    prediction_service: PredictionServiceDep, desde: datetime.date | None = None, hasta: datetime.date | None = None,
) -> CrossSellKpisResponse:
    return CrossSellKpisResponse(**prediction_service.get_conversion_kpis(desde=desde, hasta=hasta))


@router.get(
    "/cross-selling/top-combinaciones", response_model=TopCombinacionesResponse, dependencies=[Depends(vendedor_checker)],
    summary="Parejas de productos con mayor co-ocurrencia histórica en facturas (KPI accionable, no telemetría)",
)
def get_cross_sell_top_combinaciones(prediction_service: PredictionServiceDep) -> TopCombinacionesResponse:
    combinaciones = prediction_service.get_top_combinaciones()
    return TopCombinacionesResponse(combinaciones=[TopCombinacionProducto(**c) for c in combinaciones])


@router.get(
    "/cross-selling/productos", response_model=list[ProductoBusqueda], dependencies=[Depends(vendedor_checker)],
    summary="Autocompletar producto por código o nombre (asistente de Venta Cruzada)",
)
def search_cross_sell_productos(q: str, prediction_service: PredictionServiceDep) -> list[ProductoBusqueda]:
    return [ProductoBusqueda(**p) for p in prediction_service.search_productos(q)]


@router.get(
    "/cross-selling/clientes", response_model=list[ClienteBusqueda], dependencies=[Depends(vendedor_checker)],
    summary="Autocompletar cliente por cédula/RUC o nombre (asistente de Venta Cruzada)",
)
def search_cross_sell_clientes(q: str, prediction_service: PredictionServiceDep) -> list[ClienteBusqueda]:
    return [ClienteBusqueda(**c) for c in prediction_service.search_clientes(q)]
