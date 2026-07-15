# backend/tests/unit/test_analytics_service.py
"""AnalyticsService probado con repositorio mockeado (docs/auditoria/
33_actualizacion_modulo_gerencia.md, H2): `ingresos_totales` debe venir del `total_sales`
calculado en SQL por el repositorio, no reconstruirse en otra capa. Ningún test toca la BD."""
from unittest.mock import MagicMock

from app.services.analytics_service import AnalyticsService


def test_get_management_kpis_expone_ingresos_totales_del_repositorio():
    repo = MagicMock()
    repo.get_management_kpis.return_value = {
        "total_sales": 12345.678,
        "ticket": 50.0,
        "margen": 20.0,
        "branch_map": {"Matriz": 12345.678},
        "vend_map": {"Juan": 12345.678},
    }
    service = AnalyticsService(repo)

    kpis = service.get_management_kpis()

    assert kpis["ingresos_totales"] == 12345.68  # redondeado a 2 decimales
    assert kpis["ventas_por_sucursal"] == {"Matriz": 12345.678}


def test_get_management_kpis_propaga_filtros_al_repositorio():
    repo = MagicMock()
    repo.get_management_kpis.return_value = {
        "total_sales": 0.0, "ticket": 0.0, "margen": 0.0, "branch_map": {}, "vend_map": {},
    }
    service = AnalyticsService(repo)

    service.get_management_kpis(
        sucursal="GYE", start_date="2026-01-01", end_date="2026-01-31",
        categoria="REPUESTOS", vendedor="V001", almacen="A01",
    )

    repo.get_management_kpis.assert_called_once_with(
        "GYE", "2026-01-01", "2026-01-31", "REPUESTOS", "V001", "A01",
    )


# ── docs/auditoria/34_actualizacion_modulo_ventas.md, H-V3 ─────────────────────────
def test_get_sales_kpis_usa_periodo_vigente_sin_anio_mes():
    repo = MagicMock()
    repo.get_latest_period.return_value = (2026, 7)
    repo.get_sales_performance.return_value = {"meta_mensual": 0, "cumplimiento_actual": 0, "meta_proyectada": 0, "ranking_vendedores": []}
    service = AnalyticsService(repo)

    service.get_sales_kpis(sucursal="GYE")

    repo.get_latest_period.assert_called_once()
    repo.get_sales_performance.assert_called_once_with(2026, 7, "GYE")


def test_get_sales_kpis_usa_periodo_explicito_sin_consultar_el_vigente():
    repo = MagicMock()
    repo.get_sales_performance.return_value = {"meta_mensual": 0, "cumplimiento_actual": 0, "meta_proyectada": 0, "ranking_vendedores": []}
    service = AnalyticsService(repo)

    service.get_sales_kpis(sucursal="GYE", anio=2026, mes=3)

    repo.get_latest_period.assert_not_called()
    repo.get_sales_performance.assert_called_once_with(2026, 3, "GYE")
