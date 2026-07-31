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
        "roi_real": 25.0,
        "costo_mercaderia": 9876.543,
        "branch_map": {"Matriz": 12345.678},
        "vend_map": {"Juan": 12345.678},
    }
    service = AnalyticsService(repo)

    kpis = service.get_management_kpis()

    assert kpis["ingresos_totales"] == 12345.68  # redondeado a 2 decimales
    assert kpis["ventas_por_sucursal"] == {"Matriz": 12345.678}
    # docs/auditoria/39_..., H-02: el ROI viene del repositorio (RN-BI2, calculado en SQL),
    # ya no se deriva aquí multiplicando el margen por una constante.
    assert kpis["roi_real"] == 25.0
    assert kpis["roi_real"] != round(20.0 * 1.15, 2)


def test_get_management_kpis_roi_none_no_se_convierte_en_cero():
    """H-02 / criterio de aceptación de G-04: 'sin base comparable' se comunica como None,
    nunca como 0% -- un 0% se lee como 'el negocio no retorna nada', que es una afirmación
    distinta a 'no hay costo con el que calcularlo'."""
    repo = MagicMock()
    repo.get_management_kpis.return_value = {
        "total_sales": 1000.0, "ticket": 10.0, "margen": 0.0,
        "roi_real": None, "costo_mercaderia": 0.0,
        "branch_map": {}, "vend_map": {},
    }
    service = AnalyticsService(repo)

    kpis = service.get_management_kpis()

    assert kpis["roi_real"] is None


def test_get_management_kpis_propaga_filtros_al_repositorio():
    repo = MagicMock()
    repo.get_management_kpis.return_value = {
        "total_sales": 0.0, "ticket": 0.0, "margen": 0.0, "roi_real": None,
        "costo_mercaderia": 0.0, "branch_map": {}, "vend_map": {},
    }
    service = AnalyticsService(repo)

    service.get_management_kpis(
        sucursal="GYE", start_date="2026-01-01", end_date="2026-01-31",
        categoria="REPUESTOS", vendedor="V001", almacen="A01",
    )

    # Falla preexistente corregida (detectada al implementar docs/auditoria/39_...):
    # este test usaba `assert_called_once_with`, pero con `start_date`/`end_date` explícitos
    # el servicio consulta el repositorio DOS veces a propósito -- el período pedido y el
    # anterior de igual longitud, para la comparativa `*_tendencia_pct` (Fase 2 Gerencia).
    # Se verifica la primera llamada (el período pedido) y que la segunda sea la ventana previa.
    assert repo.get_management_kpis.call_count == 2
    assert repo.get_management_kpis.call_args_list[0].args == (
        "GYE", "2026-01-01", "2026-01-31", "REPUESTOS", "V001", "A01",
    )
    assert repo.get_management_kpis.call_args_list[1].args == (
        "GYE", "2025-12-01", "2025-12-31", "REPUESTOS", "V001", "A01",
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
