# backend/tests/integration/test_cross_selling_fase4.py
"""Fase 4 de docs/features/plan_refactor_venta_cruzada_ia.md: endpoint nuevo
GET /cross-selling/combos. Cubre la definición de terminado: combos con datos reales,
"un combo sin datos no se emite", RLS de cliente ajeno. Requiere Postgres real."""
import pytest

pytestmark = pytest.mark.integration

CLIENTE_AJENO = "NO-EXISTE-CLIENTE-XYZ-999"


def test_combos_rechaza_cliente_ajeno_para_ventas(client, auth_headers):
    r = client.get(
        "/api/v1/analytics/ventas/cross-selling/combos", params={"cliente_id": CLIENTE_AJENO},
        headers=auth_headers("ventas"),
    )
    assert r.status_code == 403


def test_combos_sin_cliente_devuelve_estrategias_no_dependientes_de_cliente(client, auth_headers):
    r = client.get("/api/v1/analytics/ventas/cross-selling/combos", headers=auth_headers("gerencia"))
    assert r.status_code == 200
    body = r.json()
    nombres = {c["nombre"] for c in body["combinaciones"]}
    # Sin cliente_id, "Cliente Frecuente" no puede emitirse (depende del historial de
    # UN cliente concreto) -- las demás estrategias no dependen de cliente.
    assert "Cliente Frecuente" not in nombres
    for combo in body["combinaciones"]:
        assert len(combo["productos"]) >= 2
        assert combo["porque"]


def test_combos_cada_producto_tiene_datos_reales_del_catalogo(client, auth_headers):
    r = client.get("/api/v1/analytics/ventas/cross-selling/combos", headers=auth_headers("gerencia"))
    assert r.status_code == 200
    body = r.json()
    if not body["combinaciones"]:
        pytest.skip("No hay combos con datos suficientes en el EDW de prueba.")
    for combo in body["combinaciones"]:
        for p in combo["productos"]:
            assert p["codart"]
            assert p["precio"] >= 0
