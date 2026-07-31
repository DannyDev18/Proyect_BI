# backend/tests/integration/test_warehouse_actualizacion_bodega.py
"""Fases 1-4 de docs/features/plan_actualizacion_modulo_bodega.md (ver auditoría
docs/auditoria/32_actualizacion_modulo_bodega.md): filtros E2E en reportes/Excel,
validación cerrada de tipo_movimiento, montos condicionados (RN-B8) y justificación
estadística de transferencias (RN-B9). Requiere Postgres real (ver tests/integration/conftest.py)."""
import re

import pytest

pytestmark = pytest.mark.integration


# ── Fase 1 (D1): filtros E2E en reportes/Excel ──────────────────────────────
def test_reporte_justificacion_refleja_filtros_aplicados(client, auth_headers):
    r = client.get(
        "/api/v1/analytics/bodega/reportes/justificacion",
        params={"tipo_movimiento": "FAC", "fecha_desde": "2026-01-01", "fecha_hasta": "2026-06-30"},
        headers=auth_headers("bodega"),
    )
    assert r.status_code == 200
    filtros = r.json()["filtros_aplicados"]
    assert filtros["tipo_movimiento"] == "FAC"
    assert filtros["fecha_desde"] == "2026-01-01"
    assert filtros["fecha_hasta"] == "2026-06-30"


def test_reporte_transferencias_refleja_filtros_aplicados(client, auth_headers):
    r = client.get(
        "/api/v1/analytics/bodega/reportes/transferencias",
        params={"tipo_movimiento": "TRA"},
        headers=auth_headers("bodega"),
    )
    assert r.status_code == 200
    assert r.json()["filtros_aplicados"]["tipo_movimiento"] == "TRA"


def test_reporte_analisis_mensual_refleja_filtros_aplicados(client, auth_headers):
    r = client.get(
        "/api/v1/analytics/bodega/reportes/analisis-mensual",
        params={"categoria": "NO-EXISTE-XYZ"},
        headers=auth_headers("bodega"),
    )
    assert r.status_code == 200
    assert r.json()["filtros_aplicados"]["categoria"] == "NO-EXISTE-XYZ"


# ── Fase 5: contrato tipado del reporte ─────────────────────────────────────
@pytest.mark.parametrize("tipo", ["justificacion", "transferencias", "analisis-mensual", "sin-venta", "kardex"])
def test_reporte_tiene_contrato_tipado(client, auth_headers, tipo):
    r = client.get(f"/api/v1/analytics/bodega/reportes/{tipo}", headers=auth_headers("bodega"))
    assert r.status_code == 200
    body = r.json()
    assert body["tipo"] == tipo
    assert body["titulo"]
    assert isinstance(body["resumen_ejecutivo"], list) and len(body["resumen_ejecutivo"]) >= 1
    for kpi in body["resumen_ejecutivo"]:
        assert set(kpi.keys()) == {"etiqueta", "valor", "tono"}
        assert kpi["tono"] in ("positivo", "negativo", "neutral")
    assert isinstance(body["interpretacion"], str) and len(body["interpretacion"]) > 0
    assert isinstance(body["secciones"], list) and len(body["secciones"]) >= 1
    for seccion in body["secciones"]:
        assert "titulo" in seccion and "columnas" in seccion and "filas" in seccion
        claves_columnas = {c["key"] for c in seccion["columnas"]}
        for fila in seccion["filas"][:5]:
            # cada columna declarada debe ser un campo real de la fila -- lo inverso no
            # aplica: las filas pueden traer campos extra (p.ej. `justificacion` anidada
            # en transferencias) que el frontend no muestra como columna plana.
            assert claves_columnas <= set(fila.keys())


def test_reporte_excel_acepta_los_6_filtros(client, auth_headers):
    r = client.get(
        "/api/v1/analytics/bodega/reportes/justificacion/excel",
        params={
            "almacen": "", "categoria": "", "proveedor": "",
            "tipo_movimiento": "FAC", "fecha_desde": "2026-01-01", "fecha_hasta": "2026-06-30",
        },
        headers=auth_headers("bodega"),
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ── Fase 6.2 (H-9): reporte único "artículos sin movimiento en ventas" ──────
def test_sin_venta_solo_con_stock_excluye_agotados(client, auth_headers):
    """`solo_con_stock=True` (estancados) debe ser un subconjunto de `False` (sin venta
    completo) -- nunca al revés (H-9: estancados ⊂ sin venta)."""
    headers = auth_headers("bodega")
    con_stock = client.get(
        "/api/v1/analytics/bodega/reportes/sin-venta",
        params={"solo_con_stock": True}, headers=headers,
    ).json()
    sin_filtro_stock = client.get(
        "/api/v1/analytics/bodega/reportes/sin-venta",
        params={"solo_con_stock": False}, headers=headers,
    ).json()
    filas_con_stock = con_stock["secciones"][0]["filas"]
    filas_completo = sin_filtro_stock["secciones"][0]["filas"]
    assert all(f["stock_actual"] > 0 for f in filas_con_stock)
    assert any(f["stock_actual"] <= 0 for f in filas_completo) or len(filas_completo) >= len(filas_con_stock)


def test_sin_venta_busqueda_filtra_por_codigo_o_nombre(client, auth_headers):
    # administrador (no RLS por almacén, a diferencia de "bodega") -- este test valida
    # el filtro de búsqueda en sí, no la restricción de bodegas asignadas.
    r = client.get(
        "/api/v1/analytics/bodega/reportes/sin-venta",
        params={"solo_con_stock": False, "busqueda": "HANKOOK"},
        headers=auth_headers("administrador"),
    )
    assert r.status_code == 200
    filas = r.json()["secciones"][0]["filas"]
    assert len(filas) > 0
    assert all("HANKOOK" in f["nombre"].upper() or "HANKOOK" in f["codart"].upper() for f in filas)


def test_sin_venta_expone_fecha_ultima_venta_sin_columna_cliente(client, auth_headers):
    """Decisión del usuario (§6.0 del plan): sin PII, sin columna Cliente."""
    r = client.get("/api/v1/analytics/bodega/reportes/sin-venta", headers=auth_headers("bodega"))
    columnas = {c["key"] for c in r.json()["secciones"][0]["columnas"]}
    assert "fecha_ultima_venta" in columnas
    assert "cliente" not in columnas


# ── Fase 6.7 (H-11): reporte "Movimientos de Kardex" (QUERY_KARDEX_MOVIMIENTOS) ─────
def test_kardex_expone_movimientos_con_direccion_y_existencia_global(client, auth_headers):
    r = client.get(
        "/api/v1/analytics/bodega/reportes/kardex",
        params={"fecha_desde": "2026-01-01", "fecha_hasta": "2026-06-30"},
        headers=auth_headers("administrador"),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["tipo"] == "kardex"
    columnas = {c["key"] for c in body["secciones"][0]["columnas"]}
    assert {"direccion", "existencia_global", "tipo_movimiento", "cantidad"} <= columnas
    assert "cliente" not in columnas
    for fila in body["secciones"][0]["filas"][:20]:
        assert fila["direccion"] in ("Entrada", "Salida", "N/D")
        assert "2026-01-01" <= fila["fecha"] <= "2026-06-30"


def test_kardex_filtro_tipo_movimiento_filtra_por_fila_no_por_articulo(client, auth_headers):
    """A diferencia del resto del módulo (donde `tipo_movimiento` filtra artículos que
    ALGUNA VEZ tuvieron ese tipo), en el listado de kardex cada fila debe SER de ese
    tipo -- si no, filtrar por FAC devolvería movimientos TRA/CPA de productos que
    también se vendieron alguna vez."""
    r = client.get(
        "/api/v1/analytics/bodega/reportes/kardex",
        params={"tipo_movimiento": "TRA", "fecha_desde": "2026-01-01", "fecha_hasta": "2026-06-30"},
        headers=auth_headers("administrador"),
    )
    assert r.status_code == 200
    filas = r.json()["secciones"][0]["filas"]
    assert len(filas) > 0
    assert all(f["tipo_movimiento"] == "TRA" for f in filas)


# ── Fase 6.4 (H-4): nombre de archivo Excel con fecha/hora del servidor ─────
def test_reporte_excel_incluye_fecha_hora_en_el_nombre(client, auth_headers):
    r = client.get(
        "/api/v1/analytics/bodega/reportes/analisis-mensual/excel", headers=auth_headers("bodega"),
    )
    assert r.status_code == 200
    disposicion = r.headers["content-disposition"]
    assert re.search(r"reporte_analisis-mensual_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.xlsx", disposicion)


# ── Fase 6.5 (H-3): PDF real generado en backend (reemplaza window.print()) ────
def test_reporte_pdf_devuelve_documento_real_con_fecha_hora_en_el_nombre(client, auth_headers):
    r = client.get(
        "/api/v1/analytics/bodega/reportes/analisis-mensual/pdf", headers=auth_headers("bodega"),
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    disposicion = r.headers["content-disposition"]
    assert re.search(r"reporte_analisis-mensual_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.pdf", disposicion)
    # Firma real de un PDF (no un stub/placeholder) -- confirma que WeasyPrint generó
    # bytes de PDF válidos, no solo que el endpoint respondió 200.
    assert r.content.startswith(b"%PDF-")


@pytest.mark.parametrize("tipo", ["justificacion", "transferencias", "analisis-mensual", "sin-venta", "kardex"])
def test_reporte_pdf_funciona_para_los_5_tipos(client, auth_headers, tipo):
    r = client.get(f"/api/v1/analytics/bodega/reportes/{tipo}/pdf", headers=auth_headers("administrador"))
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF-")


# ── H32-3: validación cerrada de tipo_movimiento ────────────────────────────
def test_tipo_movimiento_invalido_devuelve_400(client, auth_headers):
    r = client.get(
        "/api/v1/analytics/bodega/kpis",
        params={"tipo_movimiento": "NOEXISTE"},
        headers=auth_headers("bodega"),
    )
    assert r.status_code == 400


def test_tipo_movimiento_valido_no_falla(client, auth_headers):
    r = client.get(
        "/api/v1/analytics/bodega/kpis",
        params={"tipo_movimiento": "FAC"},
        headers=auth_headers("bodega"),
    )
    assert r.status_code == 200


# ── Fase 2 (RN-B8): montos condicionados al tipo de movimiento ─────────────
def test_top_productos_expone_monto_con_filtro_fac(client, auth_headers):
    r = client.get(
        "/api/v1/analytics/bodega/top-productos",
        params={"tipo_movimiento": "FAC", "limit": 5},
        headers=auth_headers("bodega"),
    )
    assert r.status_code == 200
    productos = r.json()
    if productos:
        assert any(p["monto_ventas"] is not None for p in productos)


def test_top_productos_sin_filtro_no_expone_monto(client, auth_headers):
    r = client.get(
        "/api/v1/analytics/bodega/top-productos",
        params={"limit": 5},
        headers=auth_headers("bodega"),
    )
    assert r.status_code == 200
    productos = r.json()
    assert all(p["monto_ventas"] is None for p in productos)


def test_top_productos_con_tipo_no_monetario_no_expone_monto(client, auth_headers):
    r = client.get(
        "/api/v1/analytics/bodega/top-productos",
        params={"tipo_movimiento": "TRA", "limit": 5},
        headers=auth_headers("bodega"),
    )
    assert r.status_code == 200
    assert all(p["monto_ventas"] is None for p in r.json())


def test_salidas_categoria_expone_monto_con_filtro_cpa(client, auth_headers):
    r = client.get(
        "/api/v1/analytics/bodega/salidas-categoria",
        params={"tipo_movimiento": "CPA"},
        headers=auth_headers("bodega"),
    )
    assert r.status_code == 200
    categorias = r.json()
    if categorias:
        assert any(c["monto_ventas"] is not None for c in categorias)


# ── Fase 4 (RN-B9): justificación estadística de transferencias ────────────
def test_transferencias_sugeridas_incluyen_justificacion_y_confianza(client, auth_headers):
    r = client.get(
        "/api/v1/analytics/bodega/transferencias-sugeridas",
        params={"page_size": 20},
        headers=auth_headers("bodega"),
    )
    assert r.status_code == 200
    sugerencias = r.json()["sugerencias"]["items"]
    for s in sugerencias:
        assert s["confianza"] in ("alta", "media", "baja")
        assert s["beneficio_neto_estimado"] is not None and s["beneficio_neto_estimado"] > 0
        justificacion = s["justificacion"]
        assert justificacion is not None
        assert justificacion["meses_con_venta_destino"] >= 2  # BODEGA_MIN_MESES_VENTA default
        assert justificacion["beneficio_neto_estimado"] == s["beneficio_neto_estimado"]
