# backend/tests/unit/test_warehouse_prediccion_compras.py
"""Predicción de compras del próximo mes por categoría (docs/auditoria/24) --
`WarehouseService.get_prediccion_compras_mes` con repos/loader fake (sin BD ni .pkl
reales, mismo patrón que test_goal_ml_service.py)."""
import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.services.warehouse_service import WarehouseService


@pytest.fixture(autouse=True)
def limpiar_cache_prediccion():
    """El cache es un dict a nivel de clase (compartido entre instancias, ver
    docs/auditoria/24) -- se limpia antes de cada test para no filtrar estado."""
    WarehouseService._prediccion_cache = {}
    yield
    WarehouseService._prediccion_cache = {}


@pytest.fixture
def warehouse_repo():
    return MagicMock()


@pytest.fixture
def dataset_repo():
    return MagicMock()


@pytest.fixture
def service(warehouse_repo, dataset_repo):
    return WarehouseService(warehouse_repo, dataset_repo, MagicMock())


def test_rango_mes_siguiente_devuelve_mes_calendario_completo(service):
    primer_dia, ultimo_dia, dias_horizonte = service._rango_mes_siguiente()
    hoy = datetime.date.today()
    assert primer_dia.day == 1
    assert primer_dia > hoy
    assert ultimo_dia.month == primer_dia.month
    assert (ultimo_dia - hoy).days == dias_horizonte


def test_prediccion_articulo_degrada_a_estadistico_si_ml_esta_vacio(service, warehouse_repo):
    primer_dia, ultimo_dia, dias_horizonte = service._rango_mes_siguiente()
    warehouse_repo.get_salidas_serie_diaria.return_value = [
        {"fecha": "2026-07-01", "unidades": 10.0},
        {"fecha": "2026-07-02", "unidades": 12.0},
    ]
    with patch.object(service, "_forecast_ml_producto", return_value=([], "estadistico")):
        filtrado, metodo = service._prediccion_articulo(
            "ART01", dias_horizonte, primer_dia, ultimo_dia, "2026-07-01", "2026-07-12",
            None, None, None,
        )
    assert metodo == "estadistico"
    assert all(primer_dia.isoformat() <= p["fecha"] <= ultimo_dia.isoformat() for p in filtrado)


def test_prediccion_articulo_recorta_al_mes_objetivo(service):
    primer_dia, ultimo_dia, dias_horizonte = service._rango_mes_siguiente()
    # Serie ML que cubre desde mañana hasta fin del mes siguiente -- debe conservar
    # solo los puntos dentro de [primer_dia, ultimo_dia].
    hoy = datetime.date.today()
    serie_completa = [
        {
            "fecha": (hoy + datetime.timedelta(days=i)).isoformat(),
            "unidades": 5.0, "banda_superior": 6.0, "banda_inferior": 4.0,
        }
        for i in range(1, dias_horizonte + 1)
    ]
    with patch.object(service, "_forecast_ml_producto", return_value=(serie_completa, "ml_demand_rf")):
        filtrado, metodo = service._prediccion_articulo(
            "ART01", dias_horizonte, primer_dia, ultimo_dia, "2026-07-01", "2026-07-12",
            None, None, None,
        )
    assert metodo == "ml_demand_rf"
    assert len(filtrado) == (ultimo_dia - primer_dia).days + 1
    assert all(primer_dia.isoformat() <= p["fecha"] <= ultimo_dia.isoformat() for p in filtrado)


def test_get_prediccion_compras_mes_drill_down_producto(service, warehouse_repo):
    warehouse_repo.get_inventario_productos.return_value = [
        {"codart": "ART01", "nombre": "Producto 1", "categoria": "REP", "stock_actual": 10.0,
         "valor_inventario": 100.0, "costo_unitario": 5.0, "punto_reorden_config": 0.0,
         "salidas_periodo": 30.0, "salidas_periodo_anterior": 20.0},
    ]
    puntos = [{"fecha": "2099-01-01", "unidades": 20.0, "banda_superior": 25.0, "banda_inferior": 15.0}]
    with patch.object(service, "_prediccion_articulo", return_value=(puntos, "ml_demand_rf")):
        resultado = service.get_prediccion_compras_mes(categoria="REP", producto_cod="ART01")

    assert resultado["producto_cod"] == "ART01"
    assert resultado["metodo"] == "ml_demand_rf"
    assert resultado["resumen"]["unidades_previstas_mes"] == 20.0
    # compra_sugerida = max(0, 20 - 10) = 10 uds * costo_unitario 5.0 = 50.0
    assert resultado["resumen"]["costo_estimado_compra"] == 50.0
    assert resultado["top_articulos"] == []


def test_get_prediccion_compras_mes_agrega_top_articulos_de_categoria(service, warehouse_repo):
    warehouse_repo.get_rotacion_productos.return_value = [
        {"codart": "A", "nombre": "Art A", "categoria": "REP", "unidades_vendidas": 100.0,
         "costo_ventas": 500.0, "margen_total": 50.0, "stock_actual": 5.0, "valor_inventario": 25.0},
        {"codart": "B", "nombre": "Art B", "categoria": "REP", "unidades_vendidas": 50.0,
         "costo_ventas": 200.0, "margen_total": 20.0, "stock_actual": 8.0, "valor_inventario": 16.0},
    ]
    warehouse_repo.get_inventario_productos.return_value = [
        {"codart": "A", "nombre": "Art A", "categoria": "REP", "stock_actual": 5.0,
         "valor_inventario": 25.0, "costo_unitario": 2.0, "punto_reorden_config": 3.0,
         "salidas_periodo": 30.0, "salidas_periodo_anterior": 25.0},
        {"codart": "B", "nombre": "Art B", "categoria": "REP", "stock_actual": 8.0,
         "valor_inventario": 16.0, "costo_unitario": 3.0, "punto_reorden_config": 0.0,
         "salidas_periodo": 15.0, "salidas_periodo_anterior": 10.0},
    ]

    def _fake_prediccion(codart, *args, **kwargs):
        if codart == "A":
            return [{"fecha": "2099-01-01", "unidades": 12.0, "banda_superior": 14.0, "banda_inferior": 10.0}], "ml_demand_rf"
        return [{"fecha": "2099-01-01", "unidades": 3.0, "banda_superior": 4.0, "banda_inferior": 2.0}], "estadistico"

    with patch.object(service, "_prediccion_articulo", side_effect=_fake_prediccion):
        resultado = service.get_prediccion_compras_mes(categoria="REP")

    assert resultado["categoria"] == "REP"
    assert resultado["metodo"] == "ml_demand_rf"  # mezcla: al menos uno con ML
    assert resultado["resumen"]["productos_incluidos"] == 2
    assert resultado["resumen"]["unidades_previstas_mes"] == pytest.approx(15.0)
    assert len(resultado["top_articulos"]) == 2
    art_a = next(a for a in resultado["top_articulos"] if a["codart"] == "A")
    assert art_a["compra_sugerida"] == pytest.approx(7.0)  # max(0, 12 - 5)
    assert resultado["serie"][0]["unidades"] == pytest.approx(15.0)  # 12 + 3 agregados por fecha


def test_get_prediccion_compras_mes_todos_degradan_a_estadistico(service, warehouse_repo):
    warehouse_repo.get_rotacion_productos.return_value = [
        {"codart": "A", "nombre": "Art A", "categoria": "REP", "unidades_vendidas": 10.0,
         "costo_ventas": 50.0, "margen_total": 5.0, "stock_actual": 1.0, "valor_inventario": 5.0},
    ]
    warehouse_repo.get_inventario_productos.return_value = []
    with patch.object(service, "_prediccion_articulo", return_value=([], "estadistico")):
        resultado = service.get_prediccion_compras_mes(categoria="REP")
    assert resultado["metodo"] == "estadistico"


def test_get_prediccion_compras_mes_usa_cache_en_llamadas_repetidas(service, warehouse_repo):
    warehouse_repo.get_rotacion_productos.return_value = [
        {"codart": "A", "nombre": "Art A", "categoria": "REP", "unidades_vendidas": 10.0,
         "costo_ventas": 50.0, "margen_total": 5.0, "stock_actual": 1.0, "valor_inventario": 5.0},
    ]
    warehouse_repo.get_inventario_productos.return_value = []
    with patch.object(service, "_prediccion_articulo", return_value=([], "estadistico")) as mock_pred:
        service.get_prediccion_compras_mes(categoria="REP")
        service.get_prediccion_compras_mes(categoria="REP")
    # Segunda llamada debe venir del cache -- no repite el cálculo por artículo.
    assert mock_pred.call_count == 1
