# backend/tests/unit/test_goal_calculation_engine.py
"""Motor v2 (docs/auditoria/46_motor_metas_configurable.md,
docs/features/plan_motor_metas_configurable.md): nivel robusto desestacionalizado ×
índice estacional (propio o de empresa) × tendencia reciente, acotado por una banda de
alcanzabilidad sobre la meta FINAL, con período objetivo explícito (nunca inferido) y
una escalera de degradación explícita según el histórico disponible."""
import pytest

from app.core.exceptions import ValidationError
from app.services.goal_calculation_engine import (
    METODO_EQUIPO_PRORRATEADO,
    METODO_ESTACIONAL_EMPRESA,
    METODO_ESTACIONAL_PROPIO,
    METODO_MADUREZ_BENCHMARK_PURO,
    METODO_MADUREZ_MEZCLA_ESTABLE,
    METODO_MADUREZ_MEZCLA_GRADUAL,
    METODO_MADUREZ_PROPIO,
    METODO_TENDENCIA_ROBUSTA,
    IQRGoalCalculationEngine,
    MetaMotorParametros,
    RegistroMensual,
    ajustar_meta_por_madurez,
)


def _mensual(anio: int, mes: int, ventas: float, unidades: float = 10.0) -> RegistroMensual:
    return RegistroMensual(anio=anio, mes=mes, ventas=ventas, unidades=unidades)


def _historico_estable(n_meses: int = 12, base: float = 1000.0, anio: int = 2025) -> list[RegistroMensual]:
    """N meses con ligera variación pero sin outliers -- caso base, empezando en enero."""
    return [_mensual(anio, m, base + (m % 3) * 10) for m in range(1, n_meses + 1)]


def _historico_multianual(n_anios: int, base: float = 1000.0, primer_anio: int = 2020) -> list[RegistroMensual]:
    """`n_anios` completos, mismo patrón cada año (para que el índice estacional propio
    tenga señal real y determinista)."""
    historico = []
    for i in range(n_anios):
        anio = primer_anio + i
        historico += [_mensual(anio, m, base + (m % 3) * 10) for m in range(1, 13)]
    return historico


@pytest.fixture
def engine() -> IQRGoalCalculationEngine:
    return IQRGoalCalculationEngine()


def test_lanza_validation_error_con_historico_vacio(engine):
    with pytest.raises(ValidationError):
        engine.calcular("VEN01", historico=[])


def test_vendedor_nuevo_con_pocos_meses_no_lanza_error(engine):
    """Caso 'vendedores nuevos o poca información histórica' del enunciado: con 1-2
    meses no hay resolución estadística (IQR/tendencia/estacionalidad), pero debe
    devolver una meta razonable en vez de bloquear la generación de la propuesta."""
    historico = [_mensual(2025, 1, 1000.0), _mensual(2025, 2, 1100.0)]

    resultado = engine.calcular("VEN01", historico=historico, anio_objetivo=2025, mes_objetivo=3)

    assert resultado.meses_historico_usados == 2
    assert resultado.metodo == METODO_EQUIPO_PRORRATEADO  # <4 meses (meses_minimos_para_iqr)
    assert resultado.meta_ventas_total > 0


def test_un_solo_mes_de_historico_no_lanza_error(engine):
    historico = [_mensual(2025, 6, 500.0)]
    resultado = engine.calcular("VEN01", historico=historico, anio_objetivo=2025, mes_objetivo=7)
    assert resultado.meta_ventas_total == pytest.approx(500.0)
    assert resultado.factor_tendencia_aplicado == pytest.approx(1.0)


def test_lanza_validation_error_con_factores_no_positivos(engine):
    historico = _historico_estable()
    with pytest.raises(ValidationError):
        engine.calcular("VEN01", historico=historico, factor_estacional=0.0)
    with pytest.raises(ValidationError):
        engine.calcular("VEN01", historico=historico, factor_crecimiento=-1.0)


def test_lanza_validation_error_si_no_hay_meses_antes_del_objetivo(engine):
    """El objetivo explícito nunca puede usar datos de su propio mes o posteriores
    (protección contra fuga) -- si toda la ventana histórica cae en o después del
    período objetivo, no hay insumo válido."""
    historico = [_mensual(2025, 6, 1000.0), _mensual(2025, 7, 1000.0)]
    with pytest.raises(ValidationError):
        engine.calcular("VEN01", historico=historico, anio_objetivo=2025, mes_objetivo=6)


# ── H-1: el período objetivo es el que pide el llamador, nunca "el siguiente al último
# dato" -- se prueba explícitamente en cada mes calendario, incluido diciembre→enero ──
@pytest.mark.parametrize("anio_obj,mes_obj", [
    (2025, 1), (2025, 6), (2025, 12), (2026, 1), (2026, 3),
])
def test_periodo_objetivo_es_siempre_el_solicitado(engine, anio_obj, mes_obj):
    historico = _historico_multianual(n_anios=2, primer_anio=2023)
    resultado = engine.calcular("VEN01", historico=historico, anio_objetivo=anio_obj, mes_objetivo=mes_obj)
    assert (resultado.anio_objetivo, resultado.mes_objetivo) == (anio_obj, mes_obj)


def test_periodo_objetivo_por_defecto_infiere_el_siguiente_mes_legado(engine):
    """Compatibilidad: sin `anio_objetivo`/`mes_objetivo` explícitos, el motor cae al
    comportamiento legado (mes siguiente al último dato) -- usado por callers que solo
    quieren 'la próxima meta razonable' sin período fijo."""
    historico = [_mensual(2025, m, 1000.0) for m in range(1, 7)]
    resultado = engine.calcular("VEN01", historico=historico)
    assert (resultado.anio_objetivo, resultado.mes_objetivo) == (2025, 7)


# ── Banda de alcanzabilidad (RN-MT3, corrige H-3): guardarraíl final ──────────────────
def test_pico_extraordinario_no_domina_la_meta(engine):
    """Un solo mes con una venta 10x el resto no debe arrastrar la meta hacia arriba --
    ni por el IQR (que puede no excluirlo) ni, sobre todo, por el techo final de la
    banda de alcanzabilidad."""
    historico = _historico_estable(n_meses=12, base=1000.0)
    historico[5] = _mensual(2025, 6, 15000.0)  # pico institucional puntual

    resultado = engine.calcular("VEN01", historico=historico, anio_objetivo=2026, mes_objetivo=1)

    # La meta debe quedar cerca del nivel normal, muy lejos del promedio "sucio" que
    # incluiría el pico -- la banda de alcanzabilidad lo garantiza aunque el IQR fallara.
    assert resultado.meta_ventas_total < 1300.0


def test_banda_de_alcanzabilidad_actua_como_techo(engine):
    """Un `factor_crecimiento` (presión comercial) exagerado no debe poder inflar la
    meta más allá del techo de la banda de alcanzabilidad -- el guardarraíl que corrige
    H-3 (antes el único techo se aplicaba ANTES de los factores de negocio)."""
    historico = _historico_estable(n_meses=12, base=1000.0)

    resultado = engine.calcular(
        "VEN01", historico=historico, anio_objetivo=2026, mes_objetivo=1,
        factor_crecimiento=3.0,  # +200%, muy por fuera de cualquier banda razonable
    )

    assert resultado.banda_actuo is True
    assert resultado.meta_ventas_total < resultado.meta_pre_banda
    assert resultado.meta_ventas_total <= resultado.referencia_alcanzable * MetaMotorParametros().banda_alcanzabilidad_max + 1e-6


def test_banda_de_alcanzabilidad_actua_como_piso(engine):
    """Simétrico: un factor de crecimiento muy bajo no debe poder hundir la meta muy
    por debajo de lo que el vendedor realmente vende -- la banda actúa en ambos
    sentidos, no solo como techo."""
    historico = _historico_estable(n_meses=12, base=1000.0)

    resultado = engine.calcular(
        "VEN01", historico=historico, anio_objetivo=2026, mes_objetivo=1,
        factor_crecimiento=0.3,  # -70%
    )

    assert resultado.banda_actuo is True
    assert resultado.meta_ventas_total > resultado.meta_pre_banda
    assert resultado.meta_ventas_total >= resultado.referencia_alcanzable * MetaMotorParametros().banda_alcanzabilidad_min - 1e-6


def test_sin_outliers_promedio_limpio_es_el_promedio_simple(engine):
    historico = [_mensual(2025, m, 1000.0) for m in range(1, 13)]
    resultado = engine.calcular("VEN01", historico=historico, anio_objetivo=2026, mes_objetivo=1)
    assert resultado.valores_atipicos_excluidos == 0
    assert resultado.promedio_historico_limpio == pytest.approx(1000.0)
    assert resultado.meta_ventas_total == pytest.approx(1000.0)


def test_aplica_factor_estacional_y_crecimiento_dentro_de_la_banda(engine):
    """Con factores moderados (dentro de la banda de alcanzabilidad), el resultado sí
    refleja el producto exacto de los factores de negocio."""
    historico = [_mensual(2025, m, 1000.0, unidades=5.0) for m in range(1, 13)]

    resultado = engine.calcular(
        "VEN01", historico=historico, anio_objetivo=2026, mes_objetivo=1,
        factor_estacional=1.05, factor_crecimiento=1.05,
    )

    assert resultado.meta_ventas_total == pytest.approx(1000.0 * 1.05 * 1.05, rel=1e-6)
    assert resultado.meta_unidades_total == pytest.approx(5.0 * 1.05 * 1.05, rel=1e-6)
    assert resultado.factor_estacional_aplicado == 1.05
    assert resultado.factor_crecimiento_aplicado == 1.05


def test_usa_la_ventana_configurada_de_meses(engine):
    """48 meses de histórico -- con la ventana por defecto (36) los 12 más antiguos
    (muy bajos, un régimen de venta ya superado) deben ignorarse."""
    historico = [_mensual(2021, m, 100.0) for m in range(1, 13)]
    historico += [_mensual(2022, m, 1000.0) for m in range(1, 13)]
    historico += [_mensual(2023, m, 1000.0) for m in range(1, 13)]
    historico += [_mensual(2024, m, 1000.0) for m in range(1, 13)]

    resultado = engine.calcular("VEN01", historico=historico, anio_objetivo=2025, mes_objetivo=1)

    assert resultado.meses_historico_usados == 36  # ventana por defecto: los 36 más recientes
    assert resultado.promedio_historico_limpio == pytest.approx(1000.0)


def test_respeta_ventana_meses_configurable(engine):
    historico = _historico_multianual(n_anios=5, base=1000.0)  # 60 meses
    parametros = MetaMotorParametros(ventana_meses=12)
    resultado = engine.calcular(
        "VEN01", historico=historico, anio_objetivo=2025, mes_objetivo=1, parametros=parametros,
    )
    assert resultado.meses_historico_usados == 12


# ── Índice estacional (RN-MT1): ratio-to-moving-average, normalizado ──────────────────
def test_indice_estacional_propio_normalizado(engine):
    """Vendedor con una estacionalidad marcada y consistente en 3 años (enero fuerte,
    julio débil): el índice estacional propio debe reflejarlo, y los índices calculados
    deben promediar 1.0 (normalización, RN-MT1)."""
    historico = []
    for anio in (2022, 2023, 2024):
        for mes in range(1, 13):
            valor = 2000.0 if mes == 1 else (500.0 if mes == 7 else 1000.0)
            historico.append(_mensual(anio, mes, valor))

    resultado_enero = engine.calcular("VEN01", historico=historico, anio_objetivo=2025, mes_objetivo=1)
    resultado_julio = engine.calcular("VEN01", historico=historico, anio_objetivo=2025, mes_objetivo=7)

    assert resultado_enero.fuente_indice_estacional == "propio"
    assert resultado_julio.fuente_indice_estacional == "propio"
    assert resultado_enero.indice_estacional_aplicado > 1.0
    assert resultado_julio.indice_estacional_aplicado < 1.0
    # Enero debe proyectar una meta mayor que julio, con el mismo histórico limpio.
    assert resultado_enero.meta_ventas_total > resultado_julio.meta_ventas_total


def test_sin_anios_suficientes_cae_a_indice_de_empresa(engine):
    """Con menos de `min_anios_estacional` (2) años del mismo mes, el índice propio no
    se calcula para ESE mes -- cae al índice de empresa si el llamador lo provee."""
    historico = _historico_estable(n_meses=10, base=1000.0)  # 1 solo año, incompleto
    indice_empresa = {m: (1.5 if m == 11 else 1.0) for m in range(1, 13)}

    resultado = engine.calcular(
        "VEN01", historico=historico, anio_objetivo=2025, mes_objetivo=11,
        indice_estacional_empresa=indice_empresa,
    )

    assert resultado.fuente_indice_estacional == "empresa"
    assert resultado.indice_estacional_aplicado == pytest.approx(1.5)


def test_sin_ningun_indice_disponible_es_neutro(engine):
    historico = _historico_estable(n_meses=6, base=1000.0)
    resultado = engine.calcular("VEN01", historico=historico, anio_objetivo=2025, mes_objetivo=7)
    assert resultado.fuente_indice_estacional == "neutro"
    assert resultado.indice_estacional_aplicado == pytest.approx(1.0)


# ── Escalera de degradación (RN-MT2, corrige H-6) ─────────────────────────────────────
def test_metodo_estacional_propio_con_historico_largo(engine):
    historico = _historico_multianual(n_anios=3)
    resultado = engine.calcular("VEN01", historico=historico, anio_objetivo=2026, mes_objetivo=1)
    assert resultado.metodo == METODO_ESTACIONAL_PROPIO


def test_metodo_estacional_empresa_sin_anios_suficientes(engine):
    historico = _historico_estable(n_meses=12, base=1000.0)
    indice_empresa = {m: 1.0 for m in range(1, 13)}
    resultado = engine.calcular(
        "VEN01", historico=historico, anio_objetivo=2026, mes_objetivo=1,
        indice_estacional_empresa=indice_empresa,
    )
    assert resultado.metodo == METODO_ESTACIONAL_EMPRESA


def test_metodo_tendencia_robusta_sin_ningun_indice(engine):
    historico = _historico_estable(n_meses=12, base=1000.0)
    resultado = engine.calcular("VEN01", historico=historico, anio_objetivo=2026, mes_objetivo=1)
    assert resultado.metodo == METODO_TENDENCIA_ROBUSTA


def test_metodo_equipo_prorrateado_con_historico_muy_corto(engine):
    historico = [_mensual(2025, 5, 1000.0), _mensual(2025, 6, 1000.0)]
    resultado = engine.calcular("VEN01", historico=historico, anio_objetivo=2025, mes_objetivo=7)
    assert resultado.metodo == METODO_EQUIPO_PRORRATEADO


def test_registra_trazabilidad_completa(engine):
    historico = _historico_estable()
    resultado = engine.calcular("VEN01", historico=historico, anio_objetivo=2026, mes_objetivo=1)
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

    resultado = engine.calcular("VEN01", historico=historico, anio_objetivo=2026, mes_objetivo=1)

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

    resultado = engine.calcular("VEN01", historico=historico, anio_objetivo=2026, mes_objetivo=1)

    assert "P_ESTRELLA" in resultado.productos_estrategicos
    assert "P_MEDIO" in resultado.productos_estrategicos
    assert "P_COLA" not in resultado.productos_estrategicos


def test_sin_detalle_de_categoria_o_producto_devuelve_listas_vacias(engine):
    historico = _historico_estable()
    resultado = engine.calcular("VEN01", historico=historico, anio_objetivo=2026, mes_objetivo=1)
    assert resultado.metas_por_categoria == []
    assert resultado.metas_por_producto == []
    assert resultado.productos_estrategicos == []


def test_mes_atipico_ml_reduce_influencia_sin_eliminarlo(engine):
    """Mecanismo genérico del motor (`meses_atipicos_ml`): un mes señalado como atípico
    pesa menos, pero NO se excluye del cálculo (a diferencia de un outlier IQR). El
    único emisor real de esta señal era el modelo `anomaly`, decomisionado por completo
    (docs/auditoria/51_...md) -- `GoalMLService` ya no la alimenta, así que este test
    ejercita el motor directamente con el parámetro explícito."""
    base = [900, 950, 1000, 1050, 1100, 1080, 1000, 1050, 900, 1000, 1050, 1000]
    historico = [_mensual(2025, m, float(v)) for m, v in zip(range(1, 13), base)]

    sin_senal_ml = engine.calcular("VEN01", historico=historico, anio_objetivo=2026, mes_objetivo=1)
    con_senal_ml = engine.calcular(
        "VEN01", historico=historico, anio_objetivo=2026, mes_objetivo=1,
        meses_atipicos_ml=frozenset({(2025, 11)}),
    )

    assert sin_senal_ml.valores_atipicos_excluidos == 0  # no es outlier IQR
    assert con_senal_ml.meses_historico_usados == sin_senal_ml.meses_historico_usados  # no se elimina
    assert con_senal_ml.meses_atipicos_ml_detectados == 1
    # Pesa menos (0.5) -> el promedio con señal ML debe ser distinto (menor) que sin ella.
    assert con_senal_ml.meta_ventas_total < sin_senal_ml.meta_ventas_total


def test_sin_senal_ml_no_detecta_meses_atipicos(engine):
    historico = _historico_estable()
    resultado = engine.calcular("VEN01", historico=historico, anio_objetivo=2026, mes_objetivo=1)
    assert resultado.meses_atipicos_ml_detectados == 0


# ── Tendencia (mecanismo conservado del motor v1, ahora sobre serie desestacionalizada) ──
def test_tendencia_creciente_sube_el_factor_dentro_del_tope(engine):
    serie_creciente = [1000.0, 1100.0, 1200.0, 1300.0]  # +10% cada mes
    factor = engine._factor_tendencia_bruto(serie_creciente, factor_min=0.85, factor_max=1.20)
    assert 1.0 < factor <= 1.20


def test_tendencia_decreciente_baja_el_factor_dentro_del_piso(engine):
    serie_decreciente = [1300.0, 1100.0, 900.0, 700.0]
    factor = engine._factor_tendencia_bruto(serie_decreciente, factor_min=0.85, factor_max=1.20)
    assert 0.85 <= factor < 1.0


def test_alta_variabilidad_atenua_el_peso_de_la_tendencia(engine):
    serie_estable = [1000.0, 1010.0, 990.0, 1005.0]
    serie_erratica = [500.0, 1800.0, 300.0, 1600.0]
    peso_estable = engine._peso_estabilidad(serie_estable, cv_alto=0.5, peso_min=0.3)
    peso_erratico = engine._peso_estabilidad(serie_erratica, cv_alto=0.5, peso_min=0.3)
    assert peso_estable == pytest.approx(1.0)
    assert peso_erratico < peso_estable
    assert peso_erratico >= 0.3


def test_meta_con_tendencia_de_crecimiento_supera_al_promedio_plano(engine):
    """Dos vendedores con el mismo promedio histórico, pero uno viene creciendo mes a
    mes recientemente: su meta debe ser mayor."""
    plano = [_mensual(2025, m, 1000.0) for m in range(1, 7)]
    creciente = [_mensual(2025, m, v) for m, v in zip(range(1, 7), [700, 820, 940, 1060, 1180, 1300])]

    resultado_plano = engine.calcular("VEN01", historico=plano, anio_objetivo=2025, mes_objetivo=7)
    resultado_creciente = engine.calcular("VEN02", historico=creciente, anio_objetivo=2025, mes_objetivo=7)

    assert resultado_creciente.meta_ventas_total > resultado_plano.meta_ventas_total


# ══════════════════════════════════════════════════════════════════════════════
# Etapa E6 -- madurez del vendedor (docs/features/plan_motor_metas_v3_y_comisiones_
# unificadas.md §10/§18-E6, R-8, auditoría 47 A-0.4): transición gradual, no un
# escalón único.
# ══════════════════════════════════════════════════════════════════════════════
def test_madurez_cero_meses_es_benchmark_puro():
    r = ajustar_meta_por_madurez(meta_propia=1000.0, benchmark_equipo=500.0, meses_antiguedad=0)
    assert r.meta_ajustada == pytest.approx(500.0)
    assert r.metodo == METODO_MADUREZ_BENCHMARK_PURO
    assert r.peso_propio == 0.0


def test_madurez_sin_dato_de_antiguedad_es_propio_puro():
    """`meses_antiguedad=None` (fecha_ingreso/histórico no disponible) se trata como
    maduro -- ausencia de dato no es lo mismo que vendedor nuevo (RN-MT9)."""
    r = ajustar_meta_por_madurez(meta_propia=1000.0, benchmark_equipo=500.0, meses_antiguedad=None)
    assert r.meta_ajustada == pytest.approx(1000.0)
    assert r.metodo == METODO_MADUREZ_PROPIO


def test_madurez_transicion_gradual_sin_salto_abrupto():
    """Con `umbral_nuevo_meses=6`, el peso propio crece linealmente 1/6, 2/6, ... 5/6 --
    nunca un salto de 0 a 1 entre dos meses consecutivos (el defecto del escalón único
    que este diseño reemplaza)."""
    pesos = [
        ajustar_meta_por_madurez(1000.0, 500.0, m, umbral_nuevo_meses=6).peso_propio
        for m in range(1, 6)
    ]
    assert pesos == pytest.approx([1 / 6, 2 / 6, 3 / 6, 4 / 6, 5 / 6])
    # Monótono creciente -- cada mes adicional de historia pesa más, nunca menos.
    assert all(pesos[i] < pesos[i + 1] for i in range(len(pesos) - 1))
    r5 = ajustar_meta_por_madurez(1000.0, 500.0, 5, umbral_nuevo_meses=6)
    assert r5.metodo == METODO_MADUREZ_MEZCLA_GRADUAL


def test_madurez_intermedia_usa_peso_fijo_configurable():
    r = ajustar_meta_por_madurez(
        meta_propia=1000.0, benchmark_equipo=0.0, meses_antiguedad=10,
        umbral_nuevo_meses=6, umbral_maduro_meses=24, peso_propio_intermedio=0.80,
    )
    assert r.metodo == METODO_MADUREZ_MEZCLA_ESTABLE
    assert r.meta_ajustada == pytest.approx(800.0)  # 0.80 * 1000 + 0.20 * 0


def test_madurez_veinticuatro_meses_o_mas_es_propio_puro():
    r = ajustar_meta_por_madurez(meta_propia=1000.0, benchmark_equipo=1.0, meses_antiguedad=24)
    assert r.metodo == METODO_MADUREZ_PROPIO
    assert r.meta_ajustada == pytest.approx(1000.0)


def test_madurez_veintitres_meses_todavia_no_es_propio_puro():
    """Frontera exacta: 23 meses cae en el tramo intermedio, 24 ya es propio puro."""
    r = ajustar_meta_por_madurez(meta_propia=1000.0, benchmark_equipo=0.0, meses_antiguedad=23)
    assert r.metodo == METODO_MADUREZ_MEZCLA_ESTABLE


# ── Interruptores del pipeline v3 (docs/features/plan_motor_metas_v3_y_comisiones_
# unificadas.md §9, Fase 6): `aplicar_*=True` (default) reproduce el motor v2 exacto --
# obligatorio para la equivalencia v2<->v3 con la configuración semilla (§19 del plan);
# `False` en cualquiera de ellos debe ser exactamente neutro para esa etapa. ─────────────
def test_pipeline_v3_con_todos_los_interruptores_en_true_reproduce_v2(engine):
    historico = _historico_multianual(n_anios=3, primer_anio=2023)
    base = engine.calcular("VEN01", historico=historico, anio_objetivo=2026, mes_objetivo=3)
    v3 = engine.calcular(
        "VEN01", historico=historico, anio_objetivo=2026, mes_objetivo=3,
        aplicar_limpieza=True, aplicar_estacionalidad=True, aplicar_tendencia=True,
        aplicar_estabilidad=True, aplicar_banda=True,
    )
    assert v3.meta_ventas_total == pytest.approx(base.meta_ventas_total)
    assert v3.metodo == base.metodo


def test_aplicar_limpieza_false_no_excluye_ningun_mes(engine):
    historico = _historico_estable(n_meses=12, base=1000.0)
    historico[5] = _mensual(2025, 6, 15000.0)  # outlier real, Tukey lo excluiría
    resultado = engine.calcular(
        "VEN01", historico=historico, anio_objetivo=2026, mes_objetivo=1, aplicar_limpieza=False,
    )
    assert resultado.valores_atipicos_excluidos == 0


def test_aplicar_estacionalidad_false_indice_siempre_neutro(engine):
    historico = _historico_multianual(n_anios=3, primer_anio=2023)
    resultado = engine.calcular(
        "VEN01", historico=historico, anio_objetivo=2026, mes_objetivo=3, aplicar_estacionalidad=False,
    )
    assert resultado.indice_estacional_aplicado == pytest.approx(1.0)
    assert resultado.fuente_indice_estacional == "neutro"


def test_aplicar_tendencia_false_factor_neutro(engine):
    historico = [_mensual(2025, m, 1000.0 + m * 50) for m in range(1, 10)]  # tendencia creciente clara
    resultado = engine.calcular(
        "VEN01", historico=historico, anio_objetivo=2025, mes_objetivo=10, aplicar_tendencia=False,
    )
    assert resultado.factor_tendencia_aplicado == pytest.approx(1.0)


def test_aplicar_estabilidad_false_no_atenua_la_tendencia(engine):
    """Serie muy errática (CV alto): con `aplicar_estabilidad=True` (default) el factor
    de tendencia se atenúa hacia 1.0; con `False`, el factor bruto actúa sin atenuar."""
    historico = [_mensual(2025, m, 1000.0 if m % 2 == 0 else 4000.0) for m in range(1, 9)]
    con_estabilidad = engine.calcular("VEN01", historico=historico, anio_objetivo=2025, mes_objetivo=9)
    sin_estabilidad = engine.calcular(
        "VEN01", historico=historico, anio_objetivo=2025, mes_objetivo=9, aplicar_estabilidad=False,
    )
    assert sin_estabilidad.factor_tendencia_aplicado != pytest.approx(con_estabilidad.factor_tendencia_aplicado)


def test_aplicar_banda_false_no_acota_la_meta(engine):
    historico = _historico_estable(n_meses=12, base=1000.0)
    historico[5] = _mensual(2025, 6, 15000.0)  # pico institucional puntual
    resultado = engine.calcular(
        "VEN01", historico=historico, anio_objetivo=2026, mes_objetivo=1, aplicar_banda=False,
    )
    assert resultado.banda_actuo is False
    assert resultado.meta_ventas_total == pytest.approx(resultado.meta_pre_banda)
