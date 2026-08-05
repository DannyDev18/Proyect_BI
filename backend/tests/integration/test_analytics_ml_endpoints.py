# backend/tests/integration/test_analytics_ml_endpoints.py
"""Migrado de `backend/test_ml_endpoints.py` (script manual sin asserts, con
credenciales hardcodeadas y login vía `urllib` contra un servidor corriendo aparte).
Ahora es un test real: usa `TestClient` (no necesita uvicorn corriendo por fuera) y
credenciales desde `tests/integration/conftest.py` (sin hardcodear en el código)."""
import pytest

pytestmark = pytest.mark.integration


def test_evolucion_mensual_ventas_gerencia(client, auth_headers):
    """Reemplaza al panel de predicción ML retirado (auditoría 49, decomisión de
    `sales_rf`): Venta Neta real mes a mes, sin ningún modelo."""
    r = client.get("/api/v1/analytics/gerencia/evolucion-mensual", headers=auth_headers("gerencia"))
    assert r.status_code == 200
    body = r.json()
    assert "serie" in body
    for punto in body["serie"]:
        assert {"anio", "mes", "venta_neta"} <= set(punto.keys())


def test_demand_forecasting_bodega(client, auth_headers):
    r = client.get("/api/v1/analytics/bodega/demand-forecasting", params={"producto_cod": "030"}, headers=auth_headers("bodega"))
    assert r.status_code == 200
    assert r.json()["producto_cod"] == "030"


def test_churn_risk_gerencia_sin_restriccion_de_cartera(client, auth_headers):
    """RN-V4 (docs/auditoria/34_actualizacion_modulo_ventas.md, H-V2): el rol `ventas`
    ya NO puede consultar un cliente arbitrario fuera de su cartera (403, cubierto en
    test_ventas_actualizacion.py) -- este test ahora usa gerencia, que conserva el
    acceso sin restricción. Antes afirmaba el comportamiento con fuga (ventas + cliente
    arbitrario -> 200)."""
    r = client.get("/api/v1/analytics/ventas/churn-risk", params={"cliente_id": "C001"}, headers=auth_headers("gerencia"))
    assert r.status_code == 200
    assert "probabilidad_abandono" in r.json()


def test_warehouse_kpis_no_es_mock(client, auth_headers):
    """Antes del refactor esta respuesta era un dict hardcodeado idéntico en cada
    llamada; ahora viene de `edw.fact_inventario_snapshot` -- solo verificamos la forma
    de la respuesta (el valor exacto depende de los datos del EDW en cada entorno)."""
    r = client.get("/api/v1/analytics/bodega/kpis-inventory", headers=auth_headers("bodega"))
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"items_sobrestock", "items_riesgo_desabasto", "transferencias_recomendadas"}
