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


# ── Fase 2 Gerencia: comparativa vs. período anterior (docs/features/plan_correcciones_pendientes.md §3) ──
def test_kpis_gerencia_sin_fechas_no_calcula_tendencia(client, auth_headers):
    """Sin start_date/end_date la vista es 'todo el histórico' -- no hay período
    anterior significativo, así que las tendencias deben venir en None (no romper el
    comportamiento por defecto ya existente de este KPI)."""
    r = client.get("/api/v1/analytics/gerencia/kpis", headers=auth_headers("gerencia"))
    assert r.status_code == 200
    body = r.json()
    assert body["ingresos_totales_tendencia_pct"] is None
    assert body["margen_utilidad_neta_tendencia_pct"] is None


def test_kpis_gerencia_con_fechas_explicitas_calcula_tendencia(client, auth_headers):
    r = client.get(
        "/api/v1/analytics/gerencia/kpis",
        params={"start_date": "2026-03-01", "end_date": "2026-03-31"},
        headers=auth_headers("gerencia"),
    )
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) >= {
        "ingresos_totales_tendencia_pct", "margen_utilidad_neta_tendencia_pct",
        "ticket_promedio_tendencia_pct", "roi_real_tendencia_pct",
    }


# ── Madurez BI: KPIs de margen/ROI saneados (docs/auditoria/39_...md, H-01/H-02) ──
def test_margen_y_roi_estan_en_rango_plausible(client, auth_headers):
    """Guardia contra H-01: el artículo Z-9001 (chatarra, `ultcos` en unidad de compra y
    cantidad vendida en kilos) aportaba el 94.9% del costo de mercadería del EDW y llevaba
    el margen publicado a -1563%. Si alguien retira la exclusión de clases, o aparece otro
    artículo con la misma patología de unidad de medida, este test lo detecta antes que un
    gerente mirando el tablero."""
    r = client.get("/api/v1/analytics/gerencia/kpis", headers=auth_headers("gerencia"))
    assert r.status_code == 200
    body = r.json()

    assert -50.0 <= body["margen_utilidad_neta"] <= 90.0, (
        f"Margen fuera de rango plausible: {body['margen_utilidad_neta']}%. "
        "Revisar ANALYTICS_CLASES_EXCLUIDAS_MARGEN y docs/auditoria/39_..., H-01."
    )
    # `roi_real` es nullable a propósito (sin costo => sin base de comparación).
    if body["roi_real"] is not None:
        assert -100.0 <= body["roi_real"] <= 500.0, f"ROI fuera de rango: {body['roi_real']}%"
    # El costo de mercadería jamás debe superar la venta neta en el agregado global:
    # es exactamente el síntoma con el que se detectó H-01 (costo = 16.6x la venta).
    assert body["costo_mercaderia"] <= body["ingresos_totales"], (
        f"Costo de mercadería ({body['costo_mercaderia']}) > ingresos ({body['ingresos_totales']}): "
        "hay un artículo con costo en unidad de medida incompatible (H-01)."
    )


def test_roi_ya_no_es_el_margen_por_una_constante(client, auth_headers):
    """H-02: `roi_estimado = margen * 1.15` fue reemplazado por RN-BI2 (retorno sobre costo
    de mercadería vendida). El contrato ya no expone el campo viejo, y el nuevo no puede ser
    un múltiplo fijo del margen."""
    r = client.get("/api/v1/analytics/gerencia/kpis", headers=auth_headers("gerencia"))
    body = r.json()
    assert "roi_estimado" not in body
    assert "roi_real" in body and "costo_mercaderia" in body
    if body["roi_real"] is not None and body["margen_utilidad_neta"]:
        assert abs(body["roi_real"] - body["margen_utilidad_neta"] * 1.15) > 0.01


# ── Fase 2 Gerencia: export Excel del dashboard (docs/features/plan_correcciones_pendientes.md §3) ──
def test_reporte_dashboard_devuelve_contrato_tipado(client, auth_headers):
    r = client.get("/api/v1/analytics/gerencia/reportes/dashboard", headers=auth_headers("gerencia"))
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) >= {"tipo", "titulo", "generado_en", "resumen_ejecutivo", "interpretacion", "secciones"}
    assert len(body["resumen_ejecutivo"]) >= 4
    assert len(body["secciones"]) == 2


def test_reporte_dashboard_rechaza_roles_no_autorizados(client, auth_headers):
    r = client.get("/api/v1/analytics/gerencia/reportes/dashboard", headers=auth_headers("ventas"))
    assert r.status_code == 403


def test_reporte_dashboard_excel_devuelve_xlsx_descargable(client, auth_headers):
    r = client.get("/api/v1/analytics/gerencia/reportes/dashboard/excel", headers=auth_headers("gerencia"))
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "attachment" in r.headers["content-disposition"]
    assert len(r.content) > 0


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
