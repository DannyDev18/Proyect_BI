# backend/tests/integration/test_venta_neta_consistencia.py
"""Guardia de la capa semántica (G-02, docs/features/plan_madurez_bi_toma_decisiones.md;
docs/auditoria/39_madurez_bi_toma_decisiones.md).

Criterio de aceptación de G-02: *"para un `(anio, mes, vendedor)` cualquiera, la venta neta
del tablero de Gerencia, la de Metas y la de Comisiones son idénticas por test automatizado"*.

Antes de esto, "venta neta" se calculaba en caminos independientes que nadie comparaba: el
de Gerencia descartaba las líneas de importe negativo (`CASE WHEN subtotal_neto > 0`) y el de
Metas/Comisiones no (`SUM(subtotal_neto)`). La divergencia era latente -- 0 líneas negativas
en 522.477 del histórico -- pero nada impedía que se activara. Ahora ambos caminos ensamblan
el mismo fragmento de `app/services/metricas/venta_neta.py`, y este test lo verifica contra
la BD real en vez de confiar en que nadie lo vuelva a separar.

Mismo patrón de test de guardia que `ml/tests/test_registry.py` y
`tests/integration/test_alembic_schema_sync.py`.
"""
import pytest
from sqlalchemy import text

from app.services.metricas.venta_neta import (
    FILTRO_ESTADO_VALIDO,
    SQL_VENTA_BRUTA,
    definicion_venta_neta,
)

pytestmark = pytest.mark.integration

# Tolerancia de redondeo entre caminos que suman en distinto orden (float en PostgreSQL).
EPSILON = 0.01


def _periodo_con_datos(db) -> tuple[int, int]:
    """Último período con ventas reales, para no fijar fechas que caduquen."""
    row = db.execute(text("""
        SELECT d.anio, d.mes
        FROM edw.fact_ventas_detalle f
        JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
        GROUP BY d.anio, d.mes
        HAVING SUM(f.subtotal_neto) > 0
        ORDER BY d.anio DESC, d.mes DESC
        LIMIT 1
    """)).fetchone()
    assert row is not None, "El EDW no tiene ventas cargadas; no se puede validar consistencia."
    return int(row[0]), int(row[1])


def test_definicion_canonica_esta_documentada():
    """La definición debe ser legible por humanos y apuntar al diccionario -- si alguien
    cambia la fórmula sin actualizar la documentación, esto lo evidencia."""
    d = definicion_venta_neta()
    assert d["nombre"] == "Venta Neta"
    assert "fact_ventas_detalle" in d["fuente"] and "fact_devoluciones" in d["fuente"]
    assert "diccionario_indicadores" in d["referencia"]
    # Regla 1: el filtro de estado forma parte de la definición, no es opcional.
    assert "estado_factura" in FILTRO_ESTADO_VALIDO
    assert "estado_documento_sk <> -1" in FILTRO_ESTADO_VALIDO


def test_venta_neta_por_vendedor_coincide_entre_metas_y_calculo_canonico(db_session):
    """Camino de Metas/Comisiones (`GoalRepository`) vs. la definición canónica aplicada
    directamente sobre el EDW."""
    from app.repositories.goal_repository import GoalRepository

    anio, mes = _periodo_con_datos(db_session)
    repo = GoalRepository(db_session)

    vendedores = repo.get_vendors_with_sales_in_period(anio, mes)
    assert vendedores, f"Sin vendedores con ventas en {mes:02d}/{anio}"

    canonico = text(f"""
        WITH ventas AS (
            SELECT {SQL_VENTA_BRUTA} AS bruta
            FROM edw.fact_ventas_detalle f
            JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
            JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
            JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
            WHERE {FILTRO_ESTADO_VALIDO}
              AND v.codven = :vendedor AND d.anio = :anio AND d.mes = :mes
        ),
        devol AS (
            SELECT COALESCE(SUM(fd.total_linea_devolucion), 0.0) AS monto
            FROM edw.fact_devoluciones fd
            JOIN edw.dim_fecha d ON fd.fecha_sk = d.fecha_sk
            JOIN edw.dim_vendedor v ON fd.vendedor_sk = v.vendedor_sk
            WHERE v.codven = :vendedor AND d.anio = :anio AND d.mes = :mes
        )
        SELECT COALESCE(ventas.bruta, 0.0) - devol.monto FROM ventas CROSS JOIN devol
    """)

    from app.core.config import settings

    revisados = 0
    for vendedor in vendedores[:15]:  # muestra acotada: la consulta canónica es por vendedor
        esperado = float(db_session.execute(canonico, {
            "vendedor": vendedor, "anio": anio, "mes": mes,
            "estado_valido": settings.ESTADO_DOCUMENTO_VALIDO,
        }).scalar() or 0.0)
        obtenido = repo.get_vendor_net_sales_period(vendedor, anio, mes)
        assert abs(obtenido - esperado) < EPSILON, (
            f"Venta neta divergente para vendedor={vendedor} {mes:02d}/{anio}: "
            f"GoalRepository={obtenido} vs. definición canónica={esperado}. "
            "Ver app/services/metricas/venta_neta.py y docs/diccionario_indicadores.md."
        )
        revisados += 1

    assert revisados > 0


def test_venta_neta_de_gerencia_coincide_con_la_suma_de_metas(client, auth_headers, db_session):
    """El KPI `ingresos_totales` de Gerencia (camino `AnalyticsRepository`) para un mes debe
    coincidir con la suma de la venta neta por vendedor del camino de Metas/Comisiones.
    Es exactamente el escenario que G-02 describe como letal: el vendedor reclama que su
    comisión no cuadra con el tablero y no hay forma de decir cuál de los dos está bien."""
    from app.repositories.goal_repository import GoalRepository

    anio, mes = _periodo_con_datos(db_session)
    ultimo_dia = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
                  7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}[mes]
    if mes == 2 and anio % 4 == 0:
        ultimo_dia = 29

    r = client.get(
        "/api/v1/analytics/gerencia/kpis",
        params={"start_date": f"{anio}-{mes:02d}-01", "end_date": f"{anio}-{mes:02d}-{ultimo_dia}"},
        headers=auth_headers("gerencia"),
    )
    assert r.status_code == 200
    gerencia = r.json()["ingresos_totales"]

    repo = GoalRepository(db_session)
    metas = sum(
        repo.get_vendor_net_sales_period(v, anio, mes)
        for v in repo.get_vendors_with_sales_in_period(anio, mes)
    )

    # Tolerancia relativa: Gerencia resta TODAS las devoluciones del período, incluidas las
    # de vendedores sin ventas en el mes (que no aparecen en `get_vendors_with_sales_in_period`).
    diferencia_pct = abs(gerencia - metas) / max(abs(gerencia), 1.0) * 100
    assert diferencia_pct < 1.0, (
        f"Venta neta de {mes:02d}/{anio} divergente entre Gerencia ({gerencia:,.2f}) y "
        f"Metas/Comisiones ({metas:,.2f}): {diferencia_pct:.2f}% de diferencia. "
        "Ambos caminos deben ensamblar app/services/metricas/venta_neta.py."
    )
