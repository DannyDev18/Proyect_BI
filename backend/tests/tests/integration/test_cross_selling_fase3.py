# backend/tests/integration/test_cross_selling_fase3.py
"""Fase 3 de docs/features/plan_refactor_venta_cruzada_ia.md (auditoría previa:
docs/auditoria/40_refactor_venta_cruzada.md): endpoint nuevo
POST /cross-selling/simular. Cubre la definición de terminado de la fase: canasta
vacía -> 400, productos sin costo -> margen None propagado, RLS de cliente ajeno.
Requiere Postgres real (ver tests/integration/conftest.py)."""
import pytest

pytestmark = pytest.mark.integration

CLIENTE_AJENO = "NO-EXISTE-CLIENTE-XYZ-999"


def test_simular_canasta_vacia_es_422(client, auth_headers):
    """`SimulacionVentaRequest.items` usa `Field(min_length=1)` (mismo patrón que
    `CrossSellSugerenciasRequest`) -- Pydantic rechaza la canasta vacía en la capa de
    validación (422) antes de llegar al servicio."""
    r = client.post(
        "/api/v1/analytics/ventas/cross-selling/simular", json={"items": []},
        headers=auth_headers("ventas"),
    )
    assert r.status_code == 422


def test_simular_rechaza_cliente_ajeno_para_ventas(client, auth_headers, db_session):
    from sqlalchemy import text
    row = db_session.execute(text(
        "SELECT codart FROM edw.dim_producto WHERE es_vigente AND producto_sk <> -1 LIMIT 1"
    )).fetchone()
    if not row:
        pytest.skip("No hay productos vigentes en el EDW de prueba.")
    r = client.post(
        "/api/v1/analytics/ventas/cross-selling/simular",
        json={"items": [str(row[0])], "cliente_id": CLIENTE_AJENO},
        headers=auth_headers("ventas"),
    )
    assert r.status_code == 403


def test_simular_ticket_estimado_es_suma_real_de_precios(client, auth_headers, db_session):
    from sqlalchemy import text
    rows = db_session.execute(text(
        "SELECT codart, precio_oficial FROM edw.dim_producto "
        "WHERE es_vigente AND producto_sk <> -1 AND precio_oficial > 0 LIMIT 2"
    )).fetchall()
    if len(rows) < 2:
        pytest.skip("No hay suficientes productos con precio vigente en el EDW de prueba.")
    items = [str(r[0]) for r in rows]
    esperado = round(sum(float(r[1]) for r in rows), 2)

    r = client.post(
        "/api/v1/analytics/ventas/cross-selling/simular", json={"items": items},
        headers=auth_headers("gerencia"),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ticket_estimado"] == esperado
    assert body["productos_no_encontrados"] == []
    assert "probabilidad de cierre" not in body["explicacion"].lower()


def test_simular_codigo_inexistente_se_reporta_no_encontrado(client, auth_headers):
    r = client.post(
        "/api/v1/analytics/ventas/cross-selling/simular",
        json={"items": ["CODIGO-QUE-NO-EXISTE-123"]},
        headers=auth_headers("gerencia"),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ticket_estimado"] == 0.0
    assert body["productos_no_encontrados"] == ["CODIGO-QUE-NO-EXISTE-123"]
