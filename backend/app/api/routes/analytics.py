# backend/app/api/routes/analytics.py
"""Gerencia: KPIs de salud comercial, ingresos por categoría, catálogos, predicción
de ventas. Los endpoints no contienen lógica de negocio -- solo validan/reciben
parámetros HTTP y delegan a `AnalyticsService`/`PredictionService`."""
from typing import Optional

from fastapi import APIRouter, Depends

from app.api.dependencies import AnalyticsServiceDep, PredictionServiceDep, audit_log, resolve_sucursal_filter
from app.core.deps import PermissionChecker
from app.schemas.analytics import GPKPIGerencia, PrediccionVentasResponse

router = APIRouter()

gerente_checker = PermissionChecker(allowed_roles=["administrador", "gerencia"])
# Gerencia: administrador/gerencia pueden elegir cualquier sucursal por query param.
sucursal_gerencia = resolve_sucursal_filter(allow_override=True)


@router.get(
    "/gerencia/kpis", response_model=GPKPIGerencia, dependencies=[Depends(gerente_checker)],
)
def get_management_kpis(
    analytics_service: AnalyticsServiceDep,
    sucursal_filtro: str | None = Depends(sucursal_gerencia),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    categoria: Optional[str] = None,
    vendedor: Optional[str] = None,
    _audit: None = Depends(audit_log(operacion="READ", tabla_afectada="all", modulo="kpis_gerencia")),
) -> GPKPIGerencia:
    """Margen de utilidad, ticket promedio, ventas consolidadas. Aplica seguridad a
    nivel de fila si el usuario es un gerente zonal."""
    kpis = analytics_service.get_management_kpis(
        sucursal=sucursal_filtro, start_date=start_date, end_date=end_date, categoria=categoria, vendedor=vendedor,
    )
    return GPKPIGerencia(**kpis)


@router.get("/gerencia/revenue-by-category", dependencies=[Depends(gerente_checker)])
def get_revenue_by_category(
    analytics_service: AnalyticsServiceDep,
    sucursal_filtro: str | None = Depends(sucursal_gerencia),
    start_date: str | None = None,
    end_date: str | None = None,
    vendedor: str | None = None,
):
    """Ingresos segmentados por categoría de producto (gráfico de barras)."""
    return analytics_service.get_revenue_by_category(
        sucursal=sucursal_filtro, start_date=start_date, end_date=end_date, vendedor=vendedor,
    )


@router.get("/gerencia/categorias", dependencies=[Depends(gerente_checker)])
def get_categories(analytics_service: AnalyticsServiceDep):
    """Lista de categorías de producto disponibles en el DW."""
    return analytics_service.get_categories()


@router.get("/gerencia/sucursales", dependencies=[Depends(gerente_checker)])
def get_sucursales(analytics_service: AnalyticsServiceDep):
    """Lista de sucursales disponibles."""
    return analytics_service.get_sucursales()


@router.get("/gerencia/vendedores", dependencies=[Depends(gerente_checker)])
def get_vendedores(analytics_service: AnalyticsServiceDep):
    """Lista de vendedores disponibles."""
    return analytics_service.get_vendedores()


@router.get(
    "/gerencia/sales-prediction", response_model=PrediccionVentasResponse,
    dependencies=[Depends(gerente_checker)],
)
def get_sales_prediction(
    prediction_service: PredictionServiceDep,
    sucursal_filtro: str | None = Depends(resolve_sucursal_filter(allow_override=False)),
) -> PrediccionVentasResponse:
    """Forecast de ventas diario/semanal vía el modelo de series de tiempo entrenado."""
    preds = prediction_service.get_sales_forecast_weekly(sucursal=sucursal_filtro)
    return PrediccionVentasResponse(
        horizonte="diario_semanal",
        dias_proyectados=preds.get("dias_proyectados", 7),
        historial_y_prediccion=preds.get("historial_y_prediccion", []),
        metricas=preds.get("metricas", {}),
        insights=preds.get("insights", []),
    )
