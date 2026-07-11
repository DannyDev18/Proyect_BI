# backend/app/api/routes/analytics.py
"""Gerencia: KPIs de salud comercial, ingresos por categoría, catálogos, predicción
de ventas. Los endpoints no contienen lógica de negocio -- solo validan/reciben
parámetros HTTP y delegan a `AnalyticsService`/`PredictionService`."""
from typing import Literal, Optional

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
    almacen: Optional[str] = None,
    _audit: None = Depends(audit_log(operacion="READ", tabla_afectada="all", modulo="kpis_gerencia")),
) -> GPKPIGerencia:
    """Margen de utilidad, ticket promedio, ventas consolidadas. Aplica seguridad a
    nivel de fila si el usuario es un gerente zonal."""
    kpis = analytics_service.get_management_kpis(
        sucursal=sucursal_filtro, start_date=start_date, end_date=end_date, categoria=categoria,
        vendedor=vendedor, almacen=almacen,
    )
    return GPKPIGerencia(**kpis)


@router.get("/gerencia/revenue-by-category", dependencies=[Depends(gerente_checker)])
def get_revenue_by_category(
    analytics_service: AnalyticsServiceDep,
    sucursal_filtro: str | None = Depends(sucursal_gerencia),
    start_date: str | None = None,
    end_date: str | None = None,
    vendedor: str | None = None,
    almacen: str | None = None,
):
    """Ingresos segmentados por categoría de producto (gráfico de barras)."""
    return analytics_service.get_revenue_by_category(
        sucursal=sucursal_filtro, start_date=start_date, end_date=end_date, vendedor=vendedor, almacen=almacen,
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


@router.get("/gerencia/almacenes", dependencies=[Depends(gerente_checker)])
def get_almacenes(analytics_service: AnalyticsServiceDep):
    """Lista de almacenes (bodegas) disponibles."""
    return analytics_service.get_almacenes()


@router.get(
    "/gerencia/sales-prediction", response_model=PrediccionVentasResponse,
    dependencies=[Depends(gerente_checker)],
)
def get_sales_prediction(
    prediction_service: PredictionServiceDep,
    sucursal_filtro: str | None = Depends(resolve_sucursal_filter(allow_override=False)),
    vendedor: Optional[str] = None,
    almacen: Optional[str] = None,
    granularidad: Literal["semana", "mes"] = "semana",
) -> PrediccionVentasResponse:
    """Forecast de ventas vía el modelo de series de tiempo entrenado (diario internamente,
    bucketizado a semana/mes según `granularidad` -- docs/auditoria/21_...md). `vendedor`/
    `almacen` filtran tanto el histórico real como la predicción (mismo criterio ya usado
    para `sucursal`, extensión documentada de H-14b)."""
    preds = prediction_service.get_sales_forecast(
        sucursal=sucursal_filtro, vendedor=vendedor, almacen=almacen, granularidad=granularidad,
    )
    return PrediccionVentasResponse(
        granularidad=preds.get("granularidad", granularidad),
        periodos_proyectados=preds.get("periodos_proyectados", 0),
        historial_y_prediccion=preds.get("historial_y_prediccion", []),
        metricas=preds.get("metricas", {}),
        insights=preds.get("insights", []),
    )
