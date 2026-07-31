# backend/tests/integration/test_analytics_ml_endpoints.py
"""Migrado de `backend/test_ml_endpoints.py` (script manual sin asserts, con
credenciales hardcodeadas y login vía `urllib` contra un servidor corriendo aparte).
Ahora es un test real: usa `TestClient` (no necesita uvicorn corriendo por fuera) y
credenciales desde `tests/integration/conftest.py` (sin hardcodear en el código)."""
import pytest

pytestmark = pytest.mark.integration


def test_sales_prediction_gerencia(client, auth_headers):
    r = client.get("/api/v1/analytics/gerencia/sales-prediction", headers=auth_headers("gerencia"))
    assert r.status_code == 200
    body = r.json()
    assert "metricas" in body
    assert "historial_y_prediccion" in body
    assert body["granularidad"] == "semana"
    assert body["periodos_proyectados"] > 0
    assert "algoritmo" in body["metricas"]


def test_sales_prediction_gerencia_granularidad_mes(client, auth_headers):
    r = client.get(
        "/api/v1/analytics/gerencia/sales-prediction",
        params={"granularidad": "mes"},
        headers=auth_headers("gerencia"),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["granularidad"] == "mes"
    assert body["periodos_proyectados"] > 0


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


def test_anomaly_detection_admin(client, auth_headers):
    r = client.get("/api/v1/analytics/admin/anomalies", params={"transaccion_id": "T001"}, headers=auth_headers("administrador"))
    assert r.status_code == 200
    assert "es_anomalia" in r.json()


def test_anomaly_detection_prohibido_para_ventas(client, auth_headers):
    """Solo administrador puede ver anomalías -- ver api/routes/admin.py."""
    r = client.get("/api/v1/analytics/admin/anomalies", params={"transaccion_id": "T001"}, headers=auth_headers("ventas"))
    assert r.status_code == 403


def test_warehouse_kpis_no_es_mock(client, auth_headers):
    """Antes del refactor esta respuesta era un dict hardcodeado idéntico en cada
    llamada; ahora viene de `edw.fact_inventario_snapshot` -- solo verificamos la forma
    de la respuesta (el valor exacto depende de los datos del EDW en cada entorno)."""
    r = client.get("/api/v1/analytics/bodega/kpis-inventory", headers=auth_headers("bodega"))
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"items_sobrestock", "items_riesgo_desabasto", "transferencias_recomendadas"}
