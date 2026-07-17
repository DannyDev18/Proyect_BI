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


# ── Fase 2 Gerencia: KPI de cumplimiento vs metas (docs/features/plan_correcciones_pendientes.md §3) ──
def test_cumplimiento_meta_periodo_devuelve_agregado_tipado(client, auth_headers):
    r = client.get(
        "/api/v1/gerencia/goals/cumplimiento", params={"anio": 2026, "mes": 3},
        headers=auth_headers("gerencia"),
    )
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) >= {
        "anio", "mes", "monto_meta_total", "venta_real_total", "pct_cumplimiento", "vendedores_con_meta_aprobada",
    }
    assert body["monto_meta_total"] >= 0
    assert body["vendedores_con_meta_aprobada"] >= 0


def test_cumplimiento_meta_periodo_sin_metas_no_lanza_division_por_cero(client, auth_headers):
    r = client.get(
        "/api/v1/gerencia/goals/cumplimiento", params={"anio": 1999, "mes": 1},
        headers=auth_headers("gerencia"),
    )
    assert r.status_code == 200
    assert r.json()["pct_cumplimiento"] == 0.0


def test_cumplimiento_meta_periodo_rechaza_roles_no_autorizados(client, auth_headers):
    r = client.get(
        "/api/v1/gerencia/goals/cumplimiento", params={"anio": 2026, "mes": 3},
        headers=auth_headers("ventas"),
    )
    assert r.status_code == 403


# ── Fase 2 Metas: transparencia del cálculo IQR (docs/features/plan_correcciones_pendientes.md §3) ──
def test_meta_sugerida_vendedor_expone_trazabilidad_del_motor(client, auth_headers):
    r = client.get(
        "/api/v1/gerencia/goals/meta-sugerida", params={"vendedor_origen": "102"},
        headers=auth_headers("gerencia"),
    )
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) >= {
        "vendedor_origen", "meta_sugerida_estadistica", "metodo_estadistico", "meses_historico_usados",
        "valores_atipicos_excluidos", "componente_estacional", "componente_tendencia",
        "factor_tendencia_aplicado", "coeficiente_variacion",
    }


def test_meta_sugerida_vendedor_rechaza_roles_no_autorizados(client, auth_headers):
    r = client.get(
        "/api/v1/gerencia/goals/meta-sugerida", params={"vendedor_origen": "102"},
        headers=auth_headers("ventas"),
    )
    assert r.status_code == 403


def test_meta_sugerida_vendedor_sin_historico_devuelve_error_de_negocio(client, auth_headers):
    r = client.get(
        "/api/v1/gerencia/goals/meta-sugerida", params={"vendedor_origen": "VENDEDOR-INEXISTENTE-9999"},
        headers=auth_headers("gerencia"),
    )
    assert r.status_code == 400
