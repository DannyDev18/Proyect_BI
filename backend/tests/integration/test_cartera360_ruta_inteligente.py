# backend/tests/integration/test_cartera360_ruta_inteligente.py
"""Fase 2 de docs/features/plan_refactor_cartera360_ruta_inteligente.md (auditoría
previa: docs/auditoria/41_refactor_cartera360.md): endpoints nuevos bajo
/analytics/ventas/ruta/*. Cubre la definición de terminado de la fase: RLS obligatoria
(R-3 del plan, "test de 403 por cada endpoint nuevo por-cliente, sin excepción") y que
la ruta priorizada responda con datos reales, no simulados. Requiere Postgres real
(ver tests/integration/conftest.py) y CARTERA360_RUTA_INTELIGENTE_ENABLED=true
(fijado por defecto en ese conftest para la suite de integración)."""
import pytest

pytestmark = pytest.mark.integration

CLIENTE_AJENO = "NO-EXISTE-CLIENTE-XYZ-999"


def test_ruta_hoy_responde_para_ventas(client, auth_headers):
    r = client.get("/api/v1/analytics/ventas/ruta/hoy", headers=auth_headers("ventas"))
    assert r.status_code == 200
    body = r.json()
    assert "tarjetas" in body and "clientes" in body
    assert isinstance(body["clientes"], list)
    assert len(body["clientes"]) <= 10  # criterio de aceptación 1 del plan


def test_ruta_hoy_rechaza_usuario_sin_codven(client, auth_headers):
    """gerencia/administrador seed no tienen id_vendedor_origen -- el propio router
    (_requerir_vendedor) debe rechazar antes de tocar el servicio."""
    r = client.get("/api/v1/analytics/ventas/ruta/hoy", headers=auth_headers("gerencia"))
    assert r.status_code == 400


def test_timeline_rechaza_cliente_ajeno_para_ventas(client, auth_headers):
    r = client.get(
        f"/api/v1/analytics/ventas/ruta/clientes/{CLIENTE_AJENO}/timeline",
        headers=auth_headers("ventas"),
    )
    assert r.status_code == 403


def test_registrar_gestion_ruta_rechaza_cliente_ajeno_para_ventas(client, auth_headers):
    r = client.post(
        "/api/v1/analytics/ventas/ruta/gestion",
        headers=auth_headers("ventas"),
        json={"cliente_id": CLIENTE_AJENO, "evento": "contactado", "canal": "llamada"},
    )
    assert r.status_code == 403


def test_registrar_gestion_ruta_rechaza_evento_invalido(client, auth_headers, db_session):
    from sqlalchemy import text
    row = db_session.execute(text("""
        SELECT l.id_cliente_transaccional
        FROM edw.fact_ventas_detalle f
        JOIN edw.dim_vendedor ve ON f.vendedor_sk = ve.vendedor_sk
        JOIN edw.dim_cliente c ON f.cliente_sk = c.cliente_sk
        JOIN public.cliente_lookup l ON c.hash_anonimo = l.hash_anonimo
        WHERE ve.codven = '102' LIMIT 1
    """)).fetchone()
    if not row:
        pytest.skip("El vendedor seed 102 no tiene clientes en el EDW de prueba.")
    r = client.post(
        "/api/v1/analytics/ventas/ruta/gestion",
        headers=auth_headers("ventas"),
        json={"cliente_id": str(row[0]), "evento": "evento_invalido_xyz"},
    )
    assert r.status_code == 400


def test_efectividad_comercial_estado_vacio_real(client, auth_headers):
    """D-1 del plan: con menos de CARTERA360_MIN_GESTIONES_EFECTIVIDAD gestiones
    reales, el panel declara tiene_datos=False -- nunca una tasa sobre muestra
    insuficiente (RN-CS5)."""
    r = client.get("/api/v1/analytics/ventas/ruta/efectividad", headers=auth_headers("ventas"))
    assert r.status_code == 200
    body = r.json()
    if not body["tiene_datos"]:
        assert body["conversion_pct"] is None
        assert body["por_canal"] == []


def test_plan_semanal_reparte_la_ruta_del_dia(client, auth_headers):
    r = client.get("/api/v1/analytics/ventas/ruta/plan-semanal", headers=auth_headers("ventas"))
    assert r.status_code == 200
    body = r.json()
    dias = {d["dia"] for d in body["dias"]}
    assert dias == {"lunes", "martes", "miercoles", "jueves", "viernes"}
