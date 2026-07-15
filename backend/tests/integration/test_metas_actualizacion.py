# backend/tests/integration/test_metas_actualizacion.py
"""Fase 1 de docs/features/plan_actualizacion_modulo_metas_comisiones.md (ver auditoría
docs/auditoria/35_actualizacion_modulo_metas.md): wiring end-to-end de `/commissions` y
`/commission-simulation` tras extraer `commission_bonus.py` y agregar
`fecha_referencia_periodo`/inmutabilidad de liquidaciones oficiales. Requiere Postgres
real (ver tests/integration/conftest.py)."""
import pytest

pytestmark = pytest.mark.integration


def test_commissions_no_lanza_con_periodo_historico(client, auth_headers):
    r = client.get(
        "/api/v1/gerencia/goals/commissions", params={"anio": 2026, "mes": 3},
        headers=auth_headers("gerencia"),
    )
    assert r.status_code == 200
    assert "comisiones" in r.json()


def test_commission_simulation_no_lanza(client, auth_headers):
    r = client.post(
        "/api/v1/gerencia/goals/commission-simulation",
        json={"meses": 1, "anio_desde": 2026, "mes_desde": 3},
        headers=auth_headers("gerencia"),
    )
    assert r.status_code == 200
    body = r.json()
    assert "costo_total_variable" in body
    assert "costo_total_plana" in body


def test_commissions_rechaza_roles_no_autorizados(client, auth_headers):
    r = client.get(
        "/api/v1/gerencia/goals/commissions", params={"anio": 2026, "mes": 3},
        headers=auth_headers("ventas"),
    )
    assert r.status_code == 403
