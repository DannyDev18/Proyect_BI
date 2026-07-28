# backend/tests/integration/test_cross_selling_fase1.py
"""Fase 1 de docs/features/plan_refactor_venta_cruzada_ia.md (auditoría previa:
docs/auditoria/40_refactor_venta_cruzada.md): endpoint nuevo
GET /cross-selling/clientes/{cliente_id}/perfil. Cubre la definición de terminado de
la fase: RLS obligatoria (decisión §3 punto 6 del plan) y el caso "cliente sin
historial" debe renderizar estado vacío real (`tiene_historial=False`, campos `None`),
nunca ceros inventados. Requiere Postgres real (ver tests/integration/conftest.py)."""
from sqlalchemy import text

import pytest

pytestmark = pytest.mark.integration

# Mismo cliente sintético que el resto de tests de RLS de este módulo (H-V2): no
# existe en public.cliente_lookup, así que la verificación de pertenencia a cartera
# (que corre ANTES que cualquier lookup de existencia) siempre falla para 'ventas'.
CLIENTE_AJENO = "NO-EXISTE-CLIENTE-XYZ-999"


def test_perfil_rechaza_cliente_ajeno_para_ventas(client, auth_headers):
    r = client.get(
        f"/api/v1/analytics/ventas/cross-selling/clientes/{CLIENTE_AJENO}/perfil",
        headers=auth_headers("ventas"),
    )
    assert r.status_code == 403


def test_perfil_cliente_inexistente_para_gerencia_es_404(client, auth_headers):
    """gerencia no tiene restricción de cartera (RLS no bloquea), pero un cliente que
    no existe en el EDW/lookup debe responder 404, no un perfil vacío inventado."""
    r = client.get(
        f"/api/v1/analytics/ventas/cross-selling/clientes/{CLIENTE_AJENO}/perfil",
        headers=auth_headers("gerencia"),
    )
    assert r.status_code == 404


def _cliente_de_cartera(db_session, codven: str) -> str | None:
    row = db_session.execute(text("""
        SELECT l.id_cliente_transaccional
        FROM edw.fact_ventas_detalle f
        JOIN edw.dim_vendedor ve ON f.vendedor_sk = ve.vendedor_sk
        JOIN edw.dim_cliente c ON f.cliente_sk = c.cliente_sk
        JOIN public.cliente_lookup l ON c.hash_anonimo = l.hash_anonimo
        WHERE ve.codven = :codven
        LIMIT 1
    """), {"codven": codven}).fetchone()
    return str(row[0]) if row else None


def test_perfil_cliente_con_historial_para_ventas(client, auth_headers, db_session):
    """Cliente real de la cartera del vendedor seed (codven 102, ventas_gye@empresa.com):
    200, tiene_historial=True y los campos numéricos vienen poblados, no None."""
    cliente_id = _cliente_de_cartera(db_session, "102")
    if not cliente_id:
        pytest.skip("El vendedor seed 102 no tiene clientes en el EDW de prueba.")
    r = client.get(
        f"/api/v1/analytics/ventas/cross-selling/clientes/{cliente_id}/perfil",
        headers=auth_headers("ventas"),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["cliente_id"] == cliente_id
    assert body["tiene_historial"] is True
    assert body["num_compras"] is not None and body["num_compras"] > 0
    assert body["valor_historico"] is not None
    assert body["probabilidad_recompra"] is not None


def _cliente_sin_ventas(db_session) -> str | None:
    row = db_session.execute(text("""
        SELECT l.id_cliente_transaccional
        FROM public.cliente_lookup l
        JOIN edw.dim_cliente c ON c.hash_anonimo = l.hash_anonimo AND c.es_vigente
        WHERE NOT EXISTS (
            SELECT 1 FROM edw.fact_ventas_detalle f WHERE f.cliente_sk = c.cliente_sk
        )
        LIMIT 1
    """)).fetchone()
    return str(row[0]) if row else None


def test_perfil_cliente_sin_historial_renderiza_estado_vacio_para_gerencia(client, auth_headers, db_session):
    """Caso R-8 del plan (arranque en frío): un cliente que existe en el EDW pero sin
    ninguna venta válida debe devolver tiene_historial=False y campos None -- nunca 0,
    que se leería como "cliente sin valor" en vez de "sin datos"."""
    cliente_id = _cliente_sin_ventas(db_session)
    if not cliente_id:
        pytest.skip("No hay clientes vigentes sin ventas en el EDW de prueba.")
    r = client.get(
        f"/api/v1/analytics/ventas/cross-selling/clientes/{cliente_id}/perfil",
        headers=auth_headers("gerencia"),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["tiene_historial"] is False
    assert body["num_compras"] is None
    assert body["valor_historico"] is None
    assert body["productos_favoritos"] == []
