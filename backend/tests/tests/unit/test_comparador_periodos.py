# backend/tests/unit/test_comparador_periodos.py
"""Comparación temporal transversal (G-04, docs/features/plan_madurez_bi_toma_decisiones.md).
Sin BD: el módulo calcula ventanas y variaciones, el caller consulta el EDW."""
from app.services.metricas.comparador import (
    ModoComparacion,
    Ventana,
    comparar,
    variacion_pct,
    ventana_anio_anterior,
    ventana_anterior,
    ventanas_de_referencia,
    ventanas_n_anteriores,
)


def test_ventana_anterior_es_contigua_y_de_igual_longitud():
    v = ventana_anterior("2026-03-01", "2026-03-31")
    assert v == Ventana("2026-01-29", "2026-02-28")
    assert v.dias == 31  # misma longitud que el período pedido
    # Contigua: termina justo el día antes del inicio del período consultado.
    assert v.hasta == "2026-02-28"


def test_ventana_anio_anterior_conserva_el_mismo_periodo():
    """Regla 11: el negocio es estacional (~31% de crecimiento 2018→2026). Comparar marzo
    contra febrero mezcla estacionalidad con tendencia; contra marzo del año pasado, no."""
    v = ventana_anio_anterior("2026-03-01", "2026-03-31")
    assert v == Ventana("2025-03-01", "2025-03-31")


def test_ventana_anio_anterior_degrada_el_29_de_febrero():
    """2024 fue bisiesto; 2023 no tiene 29 de febrero."""
    v = ventana_anio_anterior("2024-02-01", "2024-02-29")
    assert v.hasta == "2023-02-28"


def test_ventanas_n_anteriores_retrocede_sin_solaparse():
    ventanas = ventanas_n_anteriores("2026-04-01", "2026-04-30", n=3)
    assert len(ventanas) == 3
    # Cada ventana termina antes de que empiece la siguiente hacia atrás.
    for anterior, siguiente in zip(ventanas, ventanas[1:]):
        assert siguiente.hasta < anterior.desde


def test_ventanas_n_anteriores_respeta_el_tope():
    assert len(ventanas_n_anteriores("2026-04-01", "2026-04-30", n=999)) == 12
    assert len(ventanas_n_anteriores("2026-04-01", "2026-04-30", n=0)) == 1


def test_variacion_pct_sin_base_devuelve_none_no_cero():
    """Criterio de aceptación de G-04: 'sin base comparable' se comunica explícitamente.
    Un 0% se lee como 'no cambió', que es una afirmación distinta."""
    assert variacion_pct(100.0, 0.0) is None
    assert variacion_pct(100.0, -50.0) is None
    assert variacion_pct(100.0, None) is None
    assert variacion_pct(None, 100.0) is None
    assert variacion_pct(110.0, 100.0) == 10.0
    assert variacion_pct(90.0, 100.0) == -10.0


def test_comparar_promedia_las_referencias():
    ventanas = ventanas_n_anteriores("2026-04-01", "2026-04-30", n=3)
    c = comparar(120.0, [100.0, 100.0, 100.0], ModoComparacion.PROMEDIO_N_PERIODOS, ventanas)
    assert c.referencia == 100.0
    assert c.variacion_pct == 20.0
    assert c.motivo_sin_base is None


def test_comparar_ignora_periodos_sin_dato():
    """Un mes sin datos no debe arrastrar el promedio a la baja: se excluye del cálculo."""
    ventanas = ventanas_n_anteriores("2026-04-01", "2026-04-30", n=3)
    c = comparar(120.0, [100.0, None, 100.0], ModoComparacion.PROMEDIO_N_PERIODOS, ventanas)
    assert c.referencia == 100.0
    assert c.variacion_pct == 20.0


def test_comparar_explica_por_que_no_hay_base():
    ventanas = [ventana_anterior("2026-04-01", "2026-04-30")]
    sin_referencia = comparar(120.0, [None], ModoComparacion.PERIODO_ANTERIOR, ventanas)
    assert sin_referencia.variacion_pct is None
    assert "referencia" in sin_referencia.motivo_sin_base.lower()

    sin_actual = comparar(None, [100.0], ModoComparacion.PERIODO_ANTERIOR, ventanas)
    assert sin_actual.variacion_pct is None
    assert sin_actual.motivo_sin_base is not None

    referencia_cero = comparar(120.0, [0.0], ModoComparacion.PERIODO_ANTERIOR, ventanas)
    assert referencia_cero.variacion_pct is None
    assert "cero" in referencia_cero.motivo_sin_base.lower()


def test_ventanas_de_referencia_selecciona_segun_el_modo():
    desde, hasta = "2026-03-01", "2026-03-31"
    assert ventanas_de_referencia(desde, hasta, ModoComparacion.PERIODO_ANTERIOR) == [
        ventana_anterior(desde, hasta)
    ]
    assert ventanas_de_referencia(desde, hasta, ModoComparacion.ANIO_ANTERIOR) == [
        ventana_anio_anterior(desde, hasta)
    ]
    assert len(ventanas_de_referencia(desde, hasta, ModoComparacion.PROMEDIO_N_PERIODOS, n=4)) == 4
