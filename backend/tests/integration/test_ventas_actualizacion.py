# backend/tests/integration/test_ventas_actualizacion.py
"""Fase 1 de docs/features/plan_actualizacion_modulo_ventas.md (ver auditoría
docs/auditoria/34_actualizacion_modulo_ventas.md): la más importante de este archivo es
H-V2 -- confirma end-to-end que un vendedor ya no puede consultar churn/recomendaciones/
segmento/detalle de cartera de un cliente que no es suyo. Requiere Postgres real (ver
tests/integration/conftest.py)."""
import pytest

pytestmark = pytest.mark.integration

# Cliente casi con certeza fuera de la cartera del vendedor seed (ventas_gye@empresa.com,
# codven 102) -- un id inexistente/aleatorio nunca puede pertenecerle.
CLIENTE_AJENO = "NO-EXISTE-CLIENTE-XYZ-999"


def test_churn_risk_rechaza_cliente_ajeno_para_ventas(client, auth_headers):
    r = client.get(
        "/api/v1/analytics/ventas/churn-risk", params={"cliente_id": CLIENTE_AJENO},
        headers=auth_headers("ventas"),
    )
    assert r.status_code == 403


def test_recommendations_rechaza_cliente_ajeno_para_ventas(client, auth_headers):
    r = client.get(
        "/api/v1/analytics/ventas/recommendations", params={"cliente_id": CLIENTE_AJENO},
        headers=auth_headers("ventas"),
    )
    assert r.status_code == 403


def test_segmento_rechaza_cliente_ajeno_para_ventas(client, auth_headers):
    r = client.get(
        f"/api/v1/analytics/ventas/clientes/{CLIENTE_AJENO}/segmento",
        headers=auth_headers("ventas"),
    )
    assert r.status_code == 403


def test_cartera360_detalle_rechaza_cliente_ajeno(client, auth_headers):
    r = client.get(
        f"/api/v1/analytics/ventas/cartera360/clientes/{CLIENTE_AJENO}/detalle",
        headers=auth_headers("ventas"),
    )
    assert r.status_code == 403


def test_churn_risk_sin_restriccion_para_gerencia(client, auth_headers):
    """gerencia/administrador no tienen restricción de cartera -- un cliente
    inexistente responde 200 con degradación con gracia (0%), no 403."""
    r = client.get(
        "/api/v1/analytics/ventas/churn-risk", params={"cliente_id": CLIENTE_AJENO},
        headers=auth_headers("gerencia"),
    )
    assert r.status_code == 200


# ── H-V3: selector de período disponible también para ventas ───────────────────────
def test_goals_periods_accesible_para_ventas(client, auth_headers):
    r = client.get("/api/v1/gerencia/goals/periods", headers=auth_headers("ventas"))
    assert r.status_code == 200


def test_sales_goals_acepta_anio_mes_explicitos(client, auth_headers):
    r = client.get(
        "/api/v1/analytics/ventas/goals", params={"anio": 2026, "mes": 3},
        headers=auth_headers("ventas"),
    )
    assert r.status_code == 200


# ── H-V8: /analytics/ventas/goals crasheaba SIEMPRE para el rol ventas (m.sucursal no
# existe en metas_comerciales_operativas, y resolve_sucursal_filter(allow_override=False)
# fuerza la sucursal propia en cada request de ese rol) ────────────────────────────────
def test_sales_goals_no_crashea_para_ventas_sin_parametros(client, auth_headers):
    r = client.get("/api/v1/analytics/ventas/goals", headers=auth_headers("ventas"))
    assert r.status_code == 200
    body = r.json()
    assert "meta_mensual" in body and "ranking_vendedores" in body
