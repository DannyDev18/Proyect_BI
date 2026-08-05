# backend/app/api/routes/sales.py
"""Ventas: cumplimiento de metas, riesgo de churn, recomendaciones (cross-selling) y
segmentación de clientes."""
import datetime

from fastapi import APIRouter, Depends

from app.api.dependencies import (
    AnalyticsServiceDep, CommissionServiceDep, CrossSellEngineServiceDep, GoalMLServiceDep,
    PredictionServiceDep, VendorDashboardServiceDep,
)
from app.core.deps import CurrentUserDep, PermissionChecker
from app.core.exceptions import ValidationError
from app.schemas.analytics import (
    ChurnResponse, MetaSugeridaResponse, RecomendacionComercialItem,
    RecomendacionesComercialesResponse, RecomendacionProducto, RecomendacionResponse,
    SegmentacionClienteResponse, VPKPIVentas,
)
from app.schemas.commission import MiComisionResponse, PostGoalInvoiceItemResponse, PostGoalInvoicesResponse
from app.schemas.vendor_dashboard import MiNegocioResponse
from app.schemas.cross_selling import (
    ChurnExplicacionResponse, ClienteBusqueda, CombosResponse, CrossSellEventoRequest, CrossSellEventoResponse,
    CrossSellKpisResponse, CrossSellSugerenciasRequest, CrossSellSugerenciasResponse, FeatureContribucion,
    PerfilClienteResponse, ProductoBusqueda, ProductoFavorito, SimulacionVentaRequest, SimulacionVentaResponse,
    SugerenciaProducto, TopCombinacionProducto, TopCombinacionesResponse,
)

router = APIRouter()

vendedor_checker = PermissionChecker(allowed_roles=["administrador", "gerencia", "ventas"])


def _codven_restriccion(current_user: CurrentUserDep) -> str | None:
    """RLS de cartera (docs/auditoria/34_actualizacion_modulo_ventas.md, H-V2): rol
    `ventas` queda restringido a su propia cartera; gerencia/administrador consultan
    cualquier cliente (mismo criterio de privilegio que `resolve_sucursal_filter`).
    Desde la auditoría A-0.3 (decisión B-3, 2026-07-29) es también el discriminador de
    `/goals` y `/goals/forecast-cierre` -- `sucursal` se retiró de este router porque el
    90.9% de los vendedores activos transaccionan en 4-7 de las 7 sucursales reales del
    EDW (ver docstring de `AnalyticsRepository.get_sales_performance`); forzar la
    sucursal asignada al usuario le ocultaba al vendedor la mayoría de sus ventas."""
    if current_user.role.nombre in ("administrador", "gerencia"):
        return None
    return current_user.id_vendedor_origen


@router.get("/goals", response_model=VPKPIVentas, dependencies=[Depends(vendedor_checker)])
def get_sales_goals(
    analytics_service: AnalyticsServiceDep,
    codven_restriccion: str | None = Depends(_codven_restriccion),
    anio: int | None = None,
    mes: int | None = None,
) -> VPKPIVentas:
    """KPIs de ventas: metas, proyección y (para administrador/gerencia, sin
    restricción de vendedor) ranking global. Por defecto el período vigente; `anio`/
    `mes` permiten consultar un período anterior (docs/auditoria/
    34_actualizacion_modulo_ventas.md, H-V3)."""
    kpis = analytics_service.get_sales_kpis(vendedor=codven_restriccion, anio=anio, mes=mes)
    return VPKPIVentas(**kpis)


@router.get("/churn-risk", response_model=ChurnResponse, dependencies=[Depends(vendedor_checker)])
def get_churn_risk_by_client(
    cliente_id: str, prediction_service: PredictionServiceDep,
    codven_restriccion: str | None = Depends(_codven_restriccion),
) -> ChurnResponse:
    """Riesgo de abandono de un cliente vía el clasificador entrenado."""
    res = prediction_service.get_churn_risk(cliente_id, codven_restriccion)
    return ChurnResponse(cliente_id=cliente_id, probabilidad_abandono=res["probabilidad_abandono"], riesgo_alto=res["riesgo_alto"])


@router.get("/recommendations", response_model=RecomendacionResponse, dependencies=[Depends(vendedor_checker)])
def get_recommendations_for_client(
    cliente_id: str, prediction_service: PredictionServiceDep,
    codven_restriccion: str | None = Depends(_codven_restriccion),
) -> RecomendacionResponse:
    """Productos que frecuentemente se venden junto con las últimas compras del cliente."""
    res = prediction_service.get_product_recommendations(cliente_id, codven_restriccion)
    return RecomendacionResponse(
        cliente_id=cliente_id,
        recomendaciones=[RecomendacionProducto(**r) for r in res["recomendaciones"]],
    )


@router.get("/clientes/{cliente_cod}/segmento", response_model=SegmentacionClienteResponse, dependencies=[Depends(vendedor_checker)])
def get_customer_segmentation(
    cliente_cod: str, prediction_service: PredictionServiceDep,
    codven_restriccion: str | None = Depends(_codven_restriccion),
) -> SegmentacionClienteResponse:
    """Segmento comercial (RFM + K-Means) de un cliente, calculado al vuelo."""
    res = prediction_service.get_customer_segment(cliente_cod, codven_restriccion)
    return SegmentacionClienteResponse(cliente_id=cliente_cod, segmento=res["segmento"], nombre_segmento=res["nombre_segmento"])


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


@router.get(
    "/mi-negocio", response_model=MiNegocioResponse, dependencies=[Depends(vendedor_checker)],
    summary="Dashboard agregado del vendedor: cuota, comisión, ranking, tendencia, cartera en riesgo y agenda",
)
def get_mi_negocio(
    vendor_dashboard_service: VendorDashboardServiceDep, current_user: CurrentUserDep,
) -> MiNegocioResponse:
    """Auditoría 43 (H43-16, docs/auditoria/43_correcciones_sesion_ventas_y_datos.md):
    `DashboardVentas.tsx` era efectivamente un formulario de búsqueda -- ningún widget
    real hasta que el vendedor escribía un `cliente_id` exacto de memoria. Este endpoint
    compone en UNA sola llamada datos que YA existen en otros servicios (metas/comisión,
    ranking, cartera priorizada con churn_rf real, agenda de próximas acciones), sin
    ningún modelo ML nuevo ni lógica de negocio nueva de comisiones/cartera."""
    vendedor_origen = _requerir_vendedor(current_user)
    hoy = datetime.date.today()
    resultado = vendor_dashboard_service.get_mi_negocio(vendedor_origen, current_user.id, hoy.year, hoy.month)
    return MiNegocioResponse(**resultado)


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
def search_cross_sell_clientes(
    q: str, prediction_service: PredictionServiceDep,
    codven_restriccion: str | None = Depends(_codven_restriccion),
) -> list[ClienteBusqueda]:
    """RLS de cartera: un vendedor (rol `ventas`) solo puede encontrar clientes a los
    que le haya vendido alguna vez -- antes este autocompletar buscaba en todo el
    catálogo, permitiendo descubrir clientes ajenos por nombre/cédula aunque los demás
    endpoints de este router sí validaran pertenencia al consultarlos después."""
    return [ClienteBusqueda(**c) for c in prediction_service.search_clientes(q, codven_restriccion)]


@router.get(
    "/cross-selling/clientes/{cliente_id}/perfil", response_model=PerfilClienteResponse,
    dependencies=[Depends(vendedor_checker)],
    summary="Perfil 360 de un cliente (RFM, churn, valor histórico) para el asistente de Venta Cruzada",
)
def get_cross_sell_perfil_cliente(
    cliente_id: str, cross_sell_engine: CrossSellEngineServiceDep,
    codven_restriccion: str | None = Depends(_codven_restriccion),
) -> PerfilClienteResponse:
    """Fase 1 de docs/features/plan_refactor_venta_cruzada_ia.md: compone en una sola
    llamada lo que antes requería 2-3 requests separados del frontend (churn +
    segmento + agregados propios). RLS obligatoria (`_codven_restriccion`, mismo
    criterio que `/churn-risk`)."""
    perfil = cross_sell_engine.get_perfil_cliente(cliente_id, codven_restriccion)
    perfil["productos_favoritos"] = [ProductoFavorito(**p) for p in perfil["productos_favoritos"]]
    return PerfilClienteResponse(**perfil)


@router.post(
    "/cross-selling/simular", response_model=SimulacionVentaResponse, dependencies=[Depends(vendedor_checker)],
    summary="Cifras reales de la canasta que el vendedor está armando (ticket, margen, CLV)",
)
def post_cross_sell_simular(
    body: SimulacionVentaRequest, cross_sell_engine: CrossSellEngineServiceDep,
    codven_restriccion: str | None = Depends(_codven_restriccion),
) -> SimulacionVentaResponse:
    """Fase 3 de docs/features/plan_refactor_venta_cruzada_ia.md: recalcula en vivo con
    cada cambio de canasta. RLS obligatoria cuando se pasa `cliente_id`."""
    resultado = cross_sell_engine.simular_venta(body.items, body.cliente_id, codven_restriccion)
    return SimulacionVentaResponse(**resultado)


@router.get(
    "/cross-selling/combos", response_model=CombosResponse, dependencies=[Depends(vendedor_checker)],
    summary="Combos inteligentes por estrategia declarada (afinidad, margen, reincidencia, diversidad)",
)
def get_cross_sell_combos(
    cross_sell_engine: CrossSellEngineServiceDep,
    codven_restriccion: str | None = Depends(_codven_restriccion),
    cliente_id: str | None = None,
) -> CombosResponse:
    """Fase 4 de docs/features/plan_refactor_venta_cruzada_ia.md. RLS obligatoria
    cuando se pasa `cliente_id`."""
    return CombosResponse(combinaciones=cross_sell_engine.get_combos(cliente_id, codven_restriccion))


@router.get(
    "/cross-selling/clientes/{cliente_id}/explicacion-churn", response_model=ChurnExplicacionResponse,
    dependencies=[Depends(vendedor_checker)],
    summary="Explicación real (SHAP) del riesgo de abandono de un cliente -- 'Explicación del modelo', no IA generativa",
)
def get_cross_sell_explicacion_churn(
    cliente_id: str, prediction_service: PredictionServiceDep,
    codven_restriccion: str | None = Depends(_codven_restriccion),
) -> ChurnExplicacionResponse:
    """Fase 6 de docs/features/plan_refactor_venta_cruzada_ia.md (Opción A). RLS
    obligatoria, mismo criterio que `/churn-risk`."""
    contribuciones = prediction_service.get_churn_explanation(cliente_id, codven_restriccion)
    return ChurnExplicacionResponse(
        cliente_id=cliente_id, contribuciones=[FeatureContribucion(**c) for c in contribuciones],
    )
