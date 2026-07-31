# backend/tests/unit/test_commission_engine.py
import pytest

from app.services.commission_engine import (
    ConfigComisionVariable, LineaComisionable, NivelCumplimiento, RangoCredito, ReglaCategoria,
    calcular_comision, calcular_comision_variable, calcular_nivel,
)


def test_calcular_nivel_umbrales():
    assert calcular_nivel(1.2) == NivelCumplimiento.EXCELENTE
    assert calcular_nivel(1.0) == NivelCumplimiento.EXCELENTE
    assert calcular_nivel(0.99) == NivelCumplimiento.META
    assert calcular_nivel(0.9) == NivelCumplimiento.META
    assert calcular_nivel(0.89) == NivelCumplimiento.CERCA
    assert calcular_nivel(0.8) == NivelCumplimiento.CERCA
    assert calcular_nivel(0.79) == NivelCumplimiento.LEJOS
    assert calcular_nivel(0.0) == NivelCumplimiento.LEJOS


def test_lejos_no_paga_comision():
    r = calcular_comision(venta_real=5000.0, monto_meta=10000.0, comision_base_pct=7.0, bono_sobrecumplimiento=500.0)
    assert r.nivel == NivelCumplimiento.LEJOS
    assert r.tasa_aplicada_pct == 0.0
    assert r.comision_devengada == 0.0
    assert r.bono_aplicado == 0.0


def test_cerca_paga_fraccion_de_la_tasa_base_sin_bono():
    r = calcular_comision(venta_real=8500.0, monto_meta=10000.0, comision_base_pct=7.0, bono_sobrecumplimiento=500.0)
    assert r.nivel == NivelCumplimiento.CERCA
    assert r.tasa_aplicada_pct == pytest.approx(7.0 * 5.0 / 7.0)  # = 5.0
    assert r.bono_aplicado == 0.0
    assert r.comision_devengada == pytest.approx(8500.0 * 0.05)


def test_meta_paga_tasa_base_completa_sin_bono():
    r = calcular_comision(venta_real=9500.0, monto_meta=10000.0, comision_base_pct=7.0, bono_sobrecumplimiento=500.0)
    assert r.nivel == NivelCumplimiento.META
    assert r.tasa_aplicada_pct == 7.0
    assert r.bono_aplicado == 0.0
    assert r.comision_devengada == pytest.approx(9500.0 * 0.07)


def test_excelente_paga_tasa_base_mas_adicional_y_bono():
    r = calcular_comision(venta_real=12000.0, monto_meta=10000.0, comision_base_pct=7.0, bono_sobrecumplimiento=500.0)
    assert r.nivel == NivelCumplimiento.EXCELENTE
    assert r.tasa_aplicada_pct == pytest.approx(9.0)  # 7 + 2pp
    assert r.bono_aplicado == 500.0
    assert r.comision_devengada == pytest.approx(12000.0 * 0.09 + 500.0)


def test_pct_cumplimiento_reportado_en_porcentaje():
    r = calcular_comision(venta_real=7500.0, monto_meta=10000.0, comision_base_pct=7.0, bono_sobrecumplimiento=500.0)
    assert r.pct_cumplimiento == pytest.approx(75.0)


def test_sin_meta_configurada_no_divide_por_cero():
    r = calcular_comision(venta_real=5000.0, monto_meta=0.0, comision_base_pct=7.0, bono_sobrecumplimiento=500.0)
    assert r.nivel == NivelCumplimiento.LEJOS
    assert r.comision_devengada == 0.0
    assert r.pct_cumplimiento == 0.0


def test_venta_real_negativa_no_genera_comision_negativa():
    """Un vendedor con devoluciones que superan sus ventas del período (Venta Neta
    negativa) no debe generar una comisión negativa (deuda)."""
    r = calcular_comision(venta_real=-200.0, monto_meta=10000.0, comision_base_pct=7.0, bono_sobrecumplimiento=500.0)
    assert r.nivel == NivelCumplimiento.LEJOS
    assert r.comision_devengada == 0.0


def test_umbral_exacto_100_es_excelente_no_meta():
    r = calcular_comision(venta_real=10000.0, monto_meta=10000.0, comision_base_pct=7.0, bono_sobrecumplimiento=500.0)
    assert r.nivel == NivelCumplimiento.EXCELENTE


# ══════════════════════════════════════════════════════════════════════════════
# Motor Variable (docs/features/plan_integracion_comisiones_variables.md)
# ══════════════════════════════════════════════════════════════════════════════
CONFIG = ConfigComisionVariable(
    tope_descuento_pct=30.0, tasa_minima_sin_costo_pct=5.0, umbral_subtotal_x=1.0,
    mult_excelente=1.2, mult_cerca=0.7, piso_lejos=0.0,
)

MATRIZ = [
    ReglaCategoria(clase="COM", subclase=None, grupo="C", tasa_pct=5.0, base="margen", factor_estrategico=1.0),
    ReglaCategoria(clase="EQU", subclase=None, grupo="A", tasa_pct=13.0, base="margen", factor_estrategico=1.0),
    ReglaCategoria(clase="SRV", subclase=None, grupo="S", tasa_pct=6.0, base="valor", factor_estrategico=1.0),
    ReglaCategoria(clase="PRB", subclase=None, grupo="B", tasa_pct=9.0, base="margen", factor_estrategico=1.0),
]

CREDITO = [
    RangoCredito(dias_desde=0, dias_hasta=0, factor=1.0),
    RangoCredito(dias_desde=1, dias_hasta=15, factor=0.92),
    RangoCredito(dias_desde=16, dias_hasta=30, factor=0.85),
    RangoCredito(dias_desde=31, dias_hasta=45, factor=0.78),
    RangoCredito(dias_desde=46, dias_hasta=60, factor=0.70),
]


def _linea(**kwargs) -> LineaComisionable:
    base = dict(
        codart="X", clase="COM", subclase=None, es_servicio=False, subtotal_neto=1000.0,
        margen_bruto=100.0, valor_descuento=0.0, dias_plazo=0, descuento_aprobado=False,
    )
    base.update(kwargs)
    return LineaComisionable(**base)


def test_ejemplo_numerico_propuesta_grupo_a_b_c_s():
    """Golden test: docs/features/propuesta_sistema_comisiones_variables.md §5.
    3 líneas de contado: comodity C ($4.00), equipo A ($45.50), servicio S ($18.00)."""
    lineas = [
        _linea(codart="COMM", clase="COM", subtotal_neto=1000.0, margen_bruto=80.0),
        _linea(codart="EQUI", clase="EQU", subtotal_neto=1000.0, margen_bruto=350.0),
        _linea(codart="SERV", clase="SRV", es_servicio=True, subtotal_neto=300.0, margen_bruto=None),
    ]
    r = calcular_comision_variable(
        lineas=lineas, matriz=MATRIZ, rangos_credito=CREDITO, factor_tipo_vendedor=1.0,
        venta_real=52000.0, monto_meta=50000.0, devoluciones_mes=0.0, bonos_total=0.0, config=CONFIG,
    )
    assert r.comision_base == pytest.approx(4.00 + 45.50 + 18.00)
    assert r.nivel == NivelCumplimiento.EXCELENTE
    assert r.multiplicador_cumplimiento == pytest.approx(1.2)
    assert r.comision_post_cumplimiento == pytest.approx(67.50 * 1.2)
    assert r.comision_final == pytest.approx(67.50 * 1.2)


def test_factor_credito_reduce_comision_de_la_linea():
    """docs/features/nueva_propuesta_comision.md §4, Caso 2: venta a 30 días,
    margen $3.500, categoría A tasa 13% -> $455 base, factor 0.85 -> $386.75."""
    matriz = [ReglaCategoria(clase="A", subclase=None, grupo="A", tasa_pct=13.0, base="margen", factor_estrategico=1.0)]
    lineas = [_linea(codart="P1", clase="A", subtotal_neto=10000.0, margen_bruto=3500.0, dias_plazo=30)]
    r = calcular_comision_variable(
        lineas=lineas, matriz=matriz, rangos_credito=CREDITO, factor_tipo_vendedor=1.0,
        venta_real=10000.0, monto_meta=10000.0, devoluciones_mes=0.0, bonos_total=0.0, config=CONFIG,
    )
    assert r.comision_base == pytest.approx(455.0 * 0.85, rel=1e-3)


def test_linea_sin_costo_usa_tasa_minima_sobre_valor():
    lineas = [_linea(codart="SC", clase="A", subtotal_neto=500.0, margen_bruto=None)]
    r = calcular_comision_variable(
        lineas=lineas, matriz=MATRIZ, rangos_credito=CREDITO, factor_tipo_vendedor=1.0,
        venta_real=500.0, monto_meta=500.0, devoluciones_mes=0.0, bonos_total=0.0, config=CONFIG,
    )
    assert r.desglose_lineas[0].sin_costo is True
    assert r.desglose_lineas[0].tasa_pct == pytest.approx(5.0)
    assert r.comision_base == pytest.approx(500.0 * 0.05)


def test_descuento_excesivo_sin_aprobacion_no_comisiona():
    """bruto = neto + descuento = 600 + 400 = 1000 -> 40% de descuento real, por
    encima del tope del 30% (auditoría 34, H-3: el % se mide sobre el bruto, no el
    neto post-descuento)."""
    lineas = [_linea(codart="D1", clase="COM", subtotal_neto=600.0, margen_bruto=60.0, valor_descuento=400.0)]
    r = calcular_comision_variable(
        lineas=lineas, matriz=MATRIZ, rangos_credito=CREDITO, factor_tipo_vendedor=1.0,
        venta_real=1000.0, monto_meta=1000.0, devoluciones_mes=0.0, bonos_total=0.0, config=CONFIG,
    )
    assert r.desglose_lineas[0].pendiente_aprobacion is True
    assert r.comision_base == 0.0


def test_descuento_excesivo_aprobado_si_comisiona():
    lineas = [_linea(
        codart="D1", clase="COM", subtotal_neto=1000.0, margen_bruto=100.0,
        valor_descuento=400.0, descuento_aprobado=True,
    )]
    r = calcular_comision_variable(
        lineas=lineas, matriz=MATRIZ, rangos_credito=CREDITO, factor_tipo_vendedor=1.0,
        venta_real=1000.0, monto_meta=1000.0, devoluciones_mes=0.0, bonos_total=0.0, config=CONFIG,
    )
    assert r.desglose_lineas[0].pendiente_aprobacion is False
    assert r.comision_base > 0.0


def test_subtotal_casi_nulo_se_excluye_grupo_x():
    lineas = [_linea(codart="X1", clase="COM", subtotal_neto=0.50, margen_bruto=0.10)]
    r = calcular_comision_variable(
        lineas=lineas, matriz=MATRIZ, rangos_credito=CREDITO, factor_tipo_vendedor=1.0,
        venta_real=0.5, monto_meta=1000.0, devoluciones_mes=0.0, bonos_total=0.0, config=CONFIG,
    )
    assert r.desglose_lineas[0].grupo == "X"
    assert r.comision_base == 0.0


def test_factor_tipo_vendedor_interno_reduce_comision():
    lineas = [_linea(clase="COM", subtotal_neto=1000.0, margen_bruto=100.0)]
    r_externo = calcular_comision_variable(
        lineas=lineas, matriz=MATRIZ, rangos_credito=CREDITO, factor_tipo_vendedor=1.0,
        venta_real=1000.0, monto_meta=1000.0, devoluciones_mes=0.0, bonos_total=0.0, config=CONFIG,
    )
    r_interno = calcular_comision_variable(
        lineas=lineas, matriz=MATRIZ, rangos_credito=CREDITO, factor_tipo_vendedor=0.70,
        venta_real=1000.0, monto_meta=1000.0, devoluciones_mes=0.0, bonos_total=0.0, config=CONFIG,
    )
    assert r_interno.comision_post_tipo == pytest.approx(r_externo.comision_post_tipo * 0.70)


def test_piso_lejos_configurable_no_siempre_cero():
    config_con_piso = ConfigComisionVariable(
        tope_descuento_pct=30.0, tasa_minima_sin_costo_pct=5.0, umbral_subtotal_x=1.0,
        mult_excelente=1.2, mult_cerca=0.7, piso_lejos=0.4,
    )
    lineas = [_linea(clase="COM", subtotal_neto=1000.0, margen_bruto=100.0)]
    r = calcular_comision_variable(
        lineas=lineas, matriz=MATRIZ, rangos_credito=CREDITO, factor_tipo_vendedor=1.0,
        venta_real=1000.0, monto_meta=10000.0, devoluciones_mes=0.0, bonos_total=0.0, config=config_con_piso,
    )
    assert r.nivel == NivelCumplimiento.LEJOS
    assert r.comision_post_cumplimiento == pytest.approx(r.comision_post_tipo * 0.4)


def test_devoluciones_reducen_comision_final():
    lineas = [_linea(clase="COM", subtotal_neto=1000.0, margen_bruto=100.0)]
    r = calcular_comision_variable(
        lineas=lineas, matriz=MATRIZ, rangos_credito=CREDITO, factor_tipo_vendedor=1.0,
        venta_real=1000.0, monto_meta=1000.0, devoluciones_mes=200.0, bonos_total=0.0, config=CONFIG,
    )
    assert r.devoluciones_estimadas > 0.0
    assert r.comision_final < r.comision_post_cumplimiento


def test_comision_final_nunca_negativa():
    lineas = [_linea(clase="COM", subtotal_neto=10.0, margen_bruto=1.0)]
    r = calcular_comision_variable(
        lineas=lineas, matriz=MATRIZ, rangos_credito=CREDITO, factor_tipo_vendedor=1.0,
        venta_real=10.0, monto_meta=1000.0, devoluciones_mes=100000.0, bonos_total=0.0, config=CONFIG,
    )
    assert r.comision_final == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# Salvaguarda 1 -- % de descuento sobre el subtotal BRUTO, no el neto (auditoría 34,
# H-3): `subtotal_neto` ya viene post-descuento (ver etl/transformers/fact_transformer.py),
# así que el tope debe compararse contra bruto = neto + descuento.
# ══════════════════════════════════════════════════════════════════════════════
def test_descuento_25pct_sobre_bruto_no_dispara_tope_30pct():
    """bruto=1000, descuento=250 (25% real) -> neto=750. Con el denominador correcto
    (bruto) da 25% < 30 y SÍ comisiona; con el denominador viejo (neto) daba 33.3% > 30
    y se excluía incorrectamente una línea con descuento legítimo."""
    lineas = [_linea(codart="D1", clase="COM", subtotal_neto=750.0, margen_bruto=75.0, valor_descuento=250.0)]
    r = calcular_comision_variable(
        lineas=lineas, matriz=MATRIZ, rangos_credito=CREDITO, factor_tipo_vendedor=1.0,
        venta_real=750.0, monto_meta=750.0, devoluciones_mes=0.0, bonos_total=0.0, config=CONFIG,
    )
    assert r.desglose_lineas[0].pendiente_aprobacion is False
    assert r.comision_base > 0.0


def test_descuento_35pct_sobre_bruto_si_dispara_tope_30pct():
    """bruto=1000, descuento=350 (35% real) -> neto=650, por encima del tope real."""
    lineas = [_linea(codart="D2", clase="COM", subtotal_neto=650.0, margen_bruto=65.0, valor_descuento=350.0)]
    r = calcular_comision_variable(
        lineas=lineas, matriz=MATRIZ, rangos_credito=CREDITO, factor_tipo_vendedor=1.0,
        venta_real=650.0, monto_meta=650.0, devoluciones_mes=0.0, bonos_total=0.0, config=CONFIG,
    )
    assert r.desglose_lineas[0].pendiente_aprobacion is True
    assert r.comision_base == 0.0


def test_bonos_se_suman_a_la_comision_final():
    lineas = [_linea(clase="COM", subtotal_neto=1000.0, margen_bruto=100.0)]
    r = calcular_comision_variable(
        lineas=lineas, matriz=MATRIZ, rangos_credito=CREDITO, factor_tipo_vendedor=1.0,
        venta_real=1000.0, monto_meta=1000.0, devoluciones_mes=0.0, bonos_total=55.0, config=CONFIG,
    )
    assert r.bonos_total == 55.0
    assert r.comision_final == pytest.approx(r.comision_post_cumplimiento + 55.0)
