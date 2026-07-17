# backend/app/api/routes/analytics.py
"""Gerencia: KPIs de salud comercial, ingresos por categoría, catálogos, predicción
de ventas. Los endpoints no contienen lógica de negocio -- solo validan/reciben
parámetros HTTP y delegan a `AnalyticsService`/`PredictionService`."""
import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import (
    AnalyticsServiceDep, CommissionServiceDep, PredictionServiceDep, audit_log, resolve_sucursal_filter,
)
from app.core.deps import PermissionChecker
from app.schemas.analytics import GPKPIGerencia, PrediccionVentasResponse, ReporteDashboardResponse
from app.services.warehouse_export import reporte_a_excel

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


def _generar_reporte_dashboard(
    analytics_service: AnalyticsServiceDep, commission_service: CommissionServiceDep,
    sucursal_filtro: str | None, start_date: str | None, end_date: str | None,
    categoria: str | None, vendedor: str | None, almacen: str | None,
) -> dict:
    """Fase 2 Gerencia (docs/features/plan_correcciones_pendientes.md §3): compone los
    3 endpoints ya existentes (KPIs, ingresos por categoría, cumplimiento de metas) en
    el contrato tipado de reporte. Compartido entre la vista JSON y el export Excel
    (mismo patrón que `_generar_reporte` de Bodega en `warehouse.py`)."""
    kpis = analytics_service.get_management_kpis(
        sucursal=sucursal_filtro, start_date=start_date, end_date=end_date, categoria=categoria,
        vendedor=vendedor, almacen=almacen,
    )
    revenue_by_category = analytics_service.get_revenue_by_category(
        sucursal=sucursal_filtro, start_date=start_date, end_date=end_date, vendedor=vendedor, almacen=almacen,
    )
    hoy = datetime.date.today()
    cumplimiento = commission_service.get_cumplimiento_meta_periodo(anio=hoy.year, mes=hoy.month)
    filtros_aplicados = {
        "sucursal": sucursal_filtro, "start_date": start_date, "end_date": end_date,
        "categoria": categoria, "vendedor": vendedor, "almacen": almacen,
    }
    return analytics_service.get_dashboard_report(kpis, revenue_by_category, cumplimiento, filtros_aplicados)


@router.get(
    "/gerencia/reportes/dashboard", response_model=ReporteDashboardResponse, dependencies=[Depends(gerente_checker)],
)
def get_reporte_dashboard(
    analytics_service: AnalyticsServiceDep,
    commission_service: CommissionServiceDep,
    sucursal_filtro: str | None = Depends(sucursal_gerencia),
    start_date: str | None = None,
    end_date: str | None = None,
    categoria: str | None = None,
    vendedor: str | None = None,
    almacen: str | None = None,
) -> ReporteDashboardResponse:
    """Fase 2 Gerencia: reporte tipado del dashboard principal (resumen ejecutivo +
    secciones), mismo contrato que los reportes de Bodega. El frontend lo puede
    renderizar con vista imprimible (PDF vía `window.print()`, sin librería nueva)."""
    return ReporteDashboardResponse(**_generar_reporte_dashboard(
        analytics_service, commission_service, sucursal_filtro, start_date, end_date, categoria, vendedor, almacen,
    ))


@router.get("/gerencia/reportes/dashboard/excel", dependencies=[Depends(gerente_checker)])
def get_reporte_dashboard_excel(
    analytics_service: AnalyticsServiceDep,
    commission_service: CommissionServiceDep,
    sucursal_filtro: str | None = Depends(sucursal_gerencia),
    start_date: str | None = None,
    end_date: str | None = None,
    categoria: str | None = None,
    vendedor: str | None = None,
    almacen: str | None = None,
) -> Response:
    """Fase 2 Gerencia: export XLSX del reporte -- reutiliza `warehouse_export.
    reporte_a_excel` (misma hoja "Resumen" + una hoja por sección con formato de
    negocio), sin exportador nuevo."""
    contenido = _generar_reporte_dashboard(
        analytics_service, commission_service, sucursal_filtro, start_date, end_date, categoria, vendedor, almacen,
    )
    archivo = reporte_a_excel(contenido)
    return Response(
        content=archivo,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="reporte_dashboard_gerencial.xlsx"'},
    )


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
