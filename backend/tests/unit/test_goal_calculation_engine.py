# backend/tests/unit/test_goal_calculation_engine.py
import pytest

from app.core.exceptions import ValidationError
from app.services.goal_calculation_engine import (
    METODO_ESTADISTICO_IQR,
    METODO_ESTADISTICO_IQR_ML,
    IQRGoalCalculationEngine,
    RegistroMensual,
)


def _mensual(anio: int, mes: int, ventas: float, unidades: float = 10.0) -> RegistroMensual:
    return RegistroMensual(anio=anio, mes=mes, ventas=ventas, unidades=unidades)


def _historico_estable(n_meses: int = 12, base: float = 1000.0) -> list[RegistroMensual]:
    """12 meses con ligera variación pero sin outliers -- caso base."""
    return [_mensual(2025, m, base + (m % 3) * 10) for m in range(1, n_meses + 1)]


@pytest.fixture
def engine() -> IQRGoalCalculationEngine:
    return IQRGoalCalculationEngine()


def test_lanza_validation_error_con_historico_vacio(engine):
    with pytest.raises(ValidationError):
        engine.calcular("VEN01", historico=[])


def test_vendedor_nuevo_con_pocos_meses_no_lanza_error(engine):
    """Caso 'vendedores nuevos o poca información histórica' del enunciado: con 1-2 meses
    no hay resolución estadística (IQR/tendencia/estacionalidad), pero debe devolver una
    meta razonable en vez de bloquear la generación de la propuesta."""
    historico = [_mensual(2025, 1, 1000.0), _mensual(2025, 2, 1100.0)]

    resultado = engine.calcular("VEN01", historico=historico)

    assert resultado.meses_historico_usados == 2
    assert resultado.componente_estacional is None  # sin años previos con ese mes
    assert resultado.meta_ventas_total > 0


def test_un_solo_mes_de_historico_no_lanza_error(engine):
    historico = [_mensual(2025, 6, 500.0)]
    resultado = engine.calcular("VEN01", historico=historico)
    assert resultado.meta_ventas_total == pytest.approx(500.0)
    assert resultado.factor_tendencia_aplicado == pytest.approx(1.0)


def test_lanza_validation_error_con_factores_no_positivos(engine):
    historico = _historico_estable()
    with pytest.raises(ValidationError):
        engine.calcular("VEN01", historico=historico, factor_estacional=0.0)
    with pytest.raises(ValidationError):
        engine.calcular("VEN01", historico=historico, factor_crecimiento=-1.0)


def test_pico_extraordinario_no_domina_la_meta(engine):
    """Un solo mes con una venta 10x el resto no debe arrastrar la meta hacia arriba."""
    historico = _historico_estable(n_meses=12, base=1000.0)
    # Reemplaza un mes por un pico extraordinario (ej. venta institucional puntual).
    historico[5] = _mensual(2025, 6, 15000.0)

    resultado = engine.calcular("VEN01", historico=historico)

    assert resultado.valores_atipicos_excluidos >= 1
    # La meta debe quedar cerca del nivel normal (~1000-1020), lejos del promedio "sucio"
    # que incluiría el pico (~2166).
    assert resultado.meta_ventas_total < 1200.0


def test_sin_outliers_promedio_limpio_es_el_promedio_simple(engine):
    historico = [_mensual(2025, m, 1000.0) for m in range(1, 13)]

    resultado = engine.calcular("VEN01", historico=historico)

    assert resultado.valores_atipicos_excluidos == 0
    assert resultado.promedio_historico_limpio == pytest.approx(1000.0)
    assert resultado.meta_ventas_total == pytest.approx(1000.0)


def test_aplica_factor_estacional_y_crecimiento(engine):
    historico = [_mensual(2025, m, 1000.0, unidades=5.0) for m in range(1, 13)]

    resultado = engine.calcular(
        "VEN01", historico=historico, factor_estacional=1.2, factor_crecimiento=1.1,
    )

    assert resultado.meta_ventas_total == pytest.approx(1000.0 * 1.2 * 1.1)
    assert resultado.meta_unidades_total == pytest.approx(5.0 * 1.2 * 1.1)
    assert resultado.factor_estacional_aplicado == 1.2
    assert resultado.factor_crecimiento_aplicado == 1.1


def test_solo_usa_los_ultimos_24_meses(engine):
    """36 meses de histórico -- los 12 más antiguos (muy bajos) deben ignorarse."""
    historico = [_mensual(2023, m, 100.0) for m in range(1, 13)]
    historico += [_mensual(2024, m, 1000.0) for m in range(1, 13)]
    historico += [_mensual(2025, m, 1000.0) for m in range(1, 13)]

    resultado = engine.calcular("VEN01", historico=historico)

    assert resultado.meses_historico_usados == 24
    # Si los 12 meses de 2023 (venta 100) hubieran entrado, el promedio sería mucho menor.
    assert resultado.promedio_historico_limpio == pytest.approx(1000.0)


def test_registra_metodo_y_trazabilidad(engine):
    historico = _historico_estable()

    resultado = engine.calcular("VEN01", historico=historico)

    assert resultado.metodo == METODO_ESTADISTICO_IQR
    assert resultado.vendedor_origen == "VEN01"
    assert len(resultado.historico_usado) == resultado.meses_historico_usados
    assert resultado.mediana_historico > 0


def test_desglose_por_categoria_suma_a_la_meta_total(engine):
    mensual = _historico_estable()
    detalle_categoria = []
    for r in mensual:
        detalle_categoria.append(RegistroMensual(r.anio, r.mes, ventas=r.ventas * 0.6, unidades=0, categoria="Electrodomésticos"))
        detalle_categoria.append(RegistroMensual(r.anio, r.mes, ventas=r.ventas * 0.4, unidades=0, categoria="Ferretería"))
    historico = mensual + detalle_categoria

    resultado = engine.calcular("VEN01", historico=historico)

    assert {d.clave for d in resultado.metas_por_categoria} == {"Electrodomésticos", "Ferretería"}
    suma_categorias = sum(d.meta_ventas for d in resultado.metas_por_categoria)
    assert suma_categorias == pytest.approx(resultado.meta_ventas_total, rel=1e-6)
    mayor = max(resultado.metas_por_categoria, key=lambda d: d.participacion_historica_pct)
    assert mayor.clave == "Electrodomésticos"
    assert mayor.participacion_historica_pct == pytest.approx(0.6, rel=1e-2)


def test_productos_estrategicos_cubren_regla_80_20(engine):
    mensual = _historico_estable()
    detalle_producto = []
    pesos = {"P_ESTRELLA": 0.7, "P_MEDIO": 0.2, "P_COLA": 0.1}
    for r in mensual:
        for producto, peso in pesos.items():
            detalle_producto.append(RegistroMensual(r.anio, r.mes, ventas=r.ventas * peso, unidades=0, producto=producto))
    historico = mensual + detalle_producto

    resultado = engine.calcular("VEN01", historico=historico)

    assert "P_ESTRELLA" in resultado.productos_estrategicos
    assert "P_MEDIO" in resultado.productos_estrategicos
    assert "P_COLA" not in resultado.productos_estrategicos


def test_sin_detalle_de_categoria_o_producto_devuelve_listas_vacias(engine):
    historico = _historico_estable()

    resultado = engine.calcular("VEN01", historico=historico)

    assert resultado.metas_por_categoria == []
    assert resultado.metas_por_producto == []
    assert resultado.productos_estrategicos == []


def test_mes_atipico_ml_reduce_influencia_sin_eliminarlo(engine):
    """Integración ML: un mes señalado por el detector de anomalías pesa menos, pero
    NO se excluye del cálculo (a diferencia de un outlier IQR). El mes marcado (2025, 11)
    cae dentro de la ventana de tendencia reciente (últimos RECENT_TREND_MONTHS=4 meses:
    sep-oct-nov-dic/2025), que es la que determina la meta -- si se marcara un mes fuera de
    esa ventana (ej. junio), el peso no tendría efecto alguno sobre `meta_ventas_total`."""
    base = [900, 950, 1000, 1050, 1100, 1080, 1000, 1050, 900, 1000, 1050, 1000]
    historico = [_mensual(2025, m, float(v)) for m, v in zip(range(1, 13), base)]

    sin_senal_ml = engine.calcular("VEN01", historico=historico)
    con_senal_ml = engine.calcular("VEN01", historico=historico, meses_atipicos_ml=frozenset({(2025, 11)}))

    assert sin_senal_ml.valores_atipicos_excluidos == 0  # no es outlier IQR
    assert con_senal_ml.meses_historico_usados == sin_senal_ml.meses_historico_usados  # no se elimina
    assert con_senal_ml.meses_atipicos_ml_detectados == 1
    assert con_senal_ml.metodo == METODO_ESTADISTICO_IQR_ML
    # Pesa menos (0.5) -> el promedio con señal ML debe ser menor que sin ella.
    assert con_senal_ml.meta_ventas_total < sin_senal_ml.meta_ventas_total


def test_sin_senal_ml_metodo_es_el_original(engine):
    historico = _historico_estable()
    resultado = engine.calcular("VEN01", historico=historico)
    assert resultado.metodo == METODO_ESTADISTICO_IQR
    assert resultado.meses_atipicos_ml_detectados == 0


# ── Propuesta inteligente para el mes siguiente: estacionalidad + tendencia + variabilidad ──
# Estos tests llaman directamente a `_calcular_base_siguiente_mes`/`_factor_tendencia_bruto`/
# `_peso_estabilidad` (métodos internos, pero deterministas y sin acceso a datos) para aislar
# cada componente del algoritmo sin que la limpieza de outliers (IQR) de `calcular()`
# interfiera con el diseño del caso de prueba -- `calcular()` ya se cubre extremo a extremo
# arriba (pico atípico, factores externos, ventana de 24 meses).

def test_estacionalidad_usa_el_mismo_mes_de_anios_anteriores(engine):
    historico = [
        _mensual(2023, 1, 1400.0), *[_mensual(2023, m, 1000.0) for m in range(2, 13)],
        _mensual(2024, 1, 1600.0), *[_mensual(2024, m, 1000.0) for m in range(2, 13)],
    ]
    base, estacional, tendencia, _ = engine._calcular_base_siguiente_mes(
        historico, pesos=[1.0] * len(historico), valor=lambda r: r.ventas,
    )
    # Objetivo = enero (siguiente al último dato, dic/2024) -> promedio de los dos eneros.
    assert estacional == pytest.approx((1400.0 + 1600.0) / 2.0)
    # Tendencia = ventana rodante de los últimos RECENT_TREND_MONTHS (4) meses completos
    # (sep-oct-nov-dic/2024), no "todo el año en curso" -- los 4 últimos son 1000.0 parejo.
    assert tendencia == pytest.approx(1000.0)
    assert base == pytest.approx((estacional + tendencia) / 2.0)


def test_sin_anio_previo_con_el_mismo_mes_usa_solo_tendencia(engine):
    historico = [_mensual(2025, m, 1000.0 + m * 10) for m in range(1, 7)]  # solo 2025, 6 meses
    base, estacional, tendencia, _ = engine._calcular_base_siguiente_mes(
        historico, pesos=[1.0] * len(historico), valor=lambda r: r.ventas,
    )
    assert estacional is None
    assert base == pytest.approx(tendencia)


def test_tendencia_creciente_sube_el_factor_dentro_del_tope(engine):
    serie_creciente = [1000.0, 1100.0, 1200.0, 1300.0]  # +10% cada mes
    factor = engine._factor_tendencia_bruto(serie_creciente)
    assert 1.0 < factor <= 1.20  # crecimiento real, pero acotado por FACTOR_TENDENCIA_MAX


def test_tendencia_decreciente_baja_el_factor_dentro_del_piso(engine):
    serie_decreciente = [1300.0, 1100.0, 900.0, 700.0]  # caída marcada
    factor = engine._factor_tendencia_bruto(serie_decreciente)
    assert 0.85 <= factor < 1.0  # acotado por FACTOR_TENDENCIA_MIN, no colapsa a 0


def test_alta_variabilidad_atenua_el_peso_de_la_tendencia(engine):
    serie_estable = [1000.0, 1010.0, 990.0, 1005.0]
    serie_erratica = [500.0, 1800.0, 300.0, 1600.0]  # mismo orden de magnitud, muy inestable
    peso_estable = engine._peso_estabilidad(serie_estable)
    peso_erratico = engine._peso_estabilidad(serie_erratica)
    assert peso_estable == pytest.approx(1.0)
    assert peso_erratico < peso_estable
    assert peso_erratico >= 0.3  # PESO_ESTABILIDAD_MIN: nunca se anula del todo


def test_meta_con_tendencia_de_crecimiento_supera_al_promedio_plano(engine):
    """Dos vendedores con el mismo promedio histórico, pero uno viene creciendo mes a mes
    dentro del año en curso: su meta para el siguiente mes debe ser mayor."""
    plano = [_mensual(2025, m, 1000.0) for m in range(1, 7)]
    creciente = [_mensual(2025, m, v) for m, v in zip(range(1, 7), [700, 820, 940, 1060, 1180, 1300])]  # promedio = 1000

    resultado_plano = engine.calcular("VEN01", historico=plano)
    resultado_creciente = engine.calcular("VEN02", historico=creciente)

    assert resultado_creciente.meta_ventas_total > resultado_plano.meta_ventas_total
