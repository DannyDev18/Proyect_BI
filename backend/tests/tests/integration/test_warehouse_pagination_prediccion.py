# backend/tests/integration/test_warehouse_pagination_prediccion.py
"""Paginación global y predicción de compras por categoría del módulo Bodega
(docs/auditoria/24_prediccion_categoria_paginacion.md). Requiere Postgres real
(ver tests/integration/conftest.py) -- igual que el resto de tests de integración
del módulo Bodega."""
import pytest

pytestmark = pytest.mark.integration


def test_stock_reorden_paginado(client, auth_headers):
    r = client.get(
        "/api/v1/analytics/bodega/stock-reorden",
        params={"page": 1, "page_size": 5},
        headers=auth_headers("bodega"),
    )
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"items", "total", "page", "page_size", "total_pages"}
    assert body["page"] == 1
    assert body["page_size"] == 5
    assert len(body["items"]) <= 5


def test_stock_reorden_page_size_excede_tope_responde_422(client, auth_headers):
    r = client.get(
        "/api/v1/analytics/bodega/stock-reorden",
        params={"page": 1, "page_size": 9999},
        headers=auth_headers("bodega"),
    )
    assert r.status_code == 422


def test_stock_reorden_pagina_fuera_de_rango_no_falla(client, auth_headers):
    r = client.get(
        "/api/v1/analytics/bodega/stock-reorden",
        params={"page": 999999, "page_size": 10},
        headers=auth_headers("bodega"),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] >= 0


def test_necesidad_compra_recomendados_paginado(client, auth_headers):
    r = client.get(
        "/api/v1/analytics/bodega/necesidad-compra",
        params={"page": 1, "page_size": 5},
        headers=auth_headers("bodega"),
    )
    assert r.status_code == 200
    body = r.json()
    assert set(body["recomendados"].keys()) == {"items", "total", "page", "page_size", "total_pages"}
    assert isinstance(body["no_comprar"], list)
    assert "valor_total_compra" in body


def test_inventario_matriz_paginado(client, auth_headers):
    r = client.get(
        "/api/v1/analytics/bodega/inventario-matriz",
        params={"page": 1, "page_size": 5},
        headers=auth_headers("bodega"),
    )
    assert r.status_code == 200
    body = r.json()
    assert set(body["productos"].keys()) == {"items", "total", "page", "page_size", "total_pages"}
    assert "almacenes" in body


def test_transferencias_sugeridas_paginado(client, auth_headers):
    r = client.get(
        "/api/v1/analytics/bodega/transferencias-sugeridas",
        params={"page": 1, "page_size": 5},
        headers=auth_headers("bodega"),
    )
    assert r.status_code == 200
    body = r.json()
    assert set(body["sugerencias"].keys()) == {"items", "total", "page", "page_size", "total_pages"}
    assert "ahorro_total_estimado" in body


def test_prediccion_compras_mes_sin_categoria(client, auth_headers):
    r = client.get("/api/v1/analytics/bodega/prediccion-compras-mes", headers=auth_headers("bodega"))
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {
        "mes_objetivo", "categoria", "producto_cod", "metodo", "serie", "resumen", "top_articulos",
    }
    assert body["metodo"] in ("ml_demand_rf", "estadistico")
    assert len(body["top_articulos"]) <= 20


def test_prediccion_compras_mes_con_categoria(client, auth_headers):
    filtros = client.get("/api/v1/analytics/bodega/filtros", headers=auth_headers("bodega"))
    categorias = filtros.json()["categorias"]
    if not categorias:
        pytest.skip("No hay categorías en el EDW de prueba")
    r = client.get(
        "/api/v1/analytics/bodega/prediccion-compras-mes",
        params={"categoria": categorias[0]},
        headers=auth_headers("bodega"),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["categoria"] == categorias[0]
    for articulo in body["top_articulos"]:
        assert articulo["categoria"] == categorias[0]


def test_prediccion_compras_mes_drill_down_producto(client, auth_headers):
    base = client.get("/api/v1/analytics/bodega/prediccion-compras-mes", headers=auth_headers("bodega"))
    top = base.json()["top_articulos"]
    if not top:
        pytest.skip("No hay artículos con ventas en el EDW de prueba")
    codart = top[0]["codart"]
    r = client.get(
        "/api/v1/analytics/bodega/prediccion-compras-mes",
        params={"producto_cod": codart},
        headers=auth_headers("bodega"),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["producto_cod"] == codart
    assert body["top_articulos"] == []


def test_prediccion_compras_mes_gerencia_ve_todas_las_sucursales(client, auth_headers):
    """RBAC (resolve_sucursal_filter allow_override=False): gerencia no queda forzada
    a una sucursal en este endpoint, igual que el resto del módulo Bodega."""
    r = client.get("/api/v1/analytics/bodega/prediccion-compras-mes", headers=auth_headers("gerencia"))
    assert r.status_code == 200
