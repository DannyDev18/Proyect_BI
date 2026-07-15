# backend/tests/integration/test_gerencia_actualizacion.py
"""Fase 1 de docs/features/plan_actualizacion_modulo_gerencia.md (ver auditoría
docs/auditoria/33_actualizacion_modulo_gerencia.md): `ingresos_totales` en el contrato
de KPIs de Gerencia y el nuevo endpoint de procedencia de datos. Requiere Postgres real
(ver tests/integration/conftest.py)."""
import pytest

pytestmark = pytest.mark.integration


# ── H2: ingresos_totales expuesto por el backend ────────────────────────────
def test_kpis_gerencia_incluye_ingresos_totales(client, auth_headers):
    r = client.get("/api/v1/analytics/gerencia/kpis", headers=auth_headers("gerencia"))
    assert r.status_code == 200
    body = r.json()
    assert "ingresos_totales" in body
    assert isinstance(body["ingresos_totales"], (int, float))


def test_kpis_gerencia_rechaza_roles_no_autorizados(client, auth_headers):
    r = client.get("/api/v1/analytics/gerencia/kpis", headers=auth_headers("bodega"))
    assert r.status_code == 403


# ── H4: GET /system/provenance ───────────────────────────────────────────────
def test_provenance_devuelve_estado_de_modelos_para_cualquier_rol_autenticado(client, auth_headers):
    for rol in ("administrador", "gerencia", "ventas", "bodega"):
        r = client.get("/api/v1/system/provenance", headers=auth_headers(rol))
        assert r.status_code == 200
        body = r.json()
        assert "ultima_carga_dw" in body
        assert isinstance(body["modelos"], list)
        assert len(body["modelos"]) == 6
        for modelo in body["modelos"]:
            assert set(modelo.keys()) == {"nombre", "algoritmo", "entrenado_en", "activo"}


def test_provenance_rechaza_sin_token(client):
    r = client.get("/api/v1/system/provenance")
    assert r.status_code == 401
