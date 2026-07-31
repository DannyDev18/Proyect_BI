# backend/tests/unit/test_commission_cobranza_engine.py
"""Tests del motor de Comisión sobre Cobros y de la fórmula editable (auditoría 44,
docs/auditoria/44_comisiones_sobre_cobros.md; docs/features/plan_comisiones_sobre_cobros.md).
Los tramos y la comisión de referencia reproducen la verdad de campo de febrero-2026
verificada contra Producción (auditoría 44 §3, vendedor VEN13)."""
import pytest

from app.services.commission_engine import (
    CobroComisionable, PasoFormula, TramoCobranza, calcular_comision_cobranza, calcular_contado_agencia,
    evaluar_formula, resolver_tramo_cobranza,
)

TRAMOS_EXTERNO = [
    TramoCobranza(dias_hasta=21, tasa_pct=2.0),
    TramoCobranza(dias_hasta=60, tasa_pct=1.75),
    TramoCobranza(dias_hasta=90, tasa_pct=0.75),
    TramoCobranza(dias_hasta=120, tasa_pct=0.50),
    TramoCobranza(dias_hasta=365, tasa_pct=0.00),
]


# ── resolver_tramo_cobranza ──────────────────────────────────────────────────────
def test_resolver_tramo_cobranza_limites_exactos():
    assert resolver_tramo_cobranza(21, TRAMOS_EXTERNO) == 2.0
    assert resolver_tramo_cobranza(22, TRAMOS_EXTERNO) == 1.75
    assert resolver_tramo_cobranza(60, TRAMOS_EXTERNO) == 1.75
    assert resolver_tramo_cobranza(61, TRAMOS_EXTERNO) == 0.75
    assert resolver_tramo_cobranza(120, TRAMOS_EXTERNO) == 0.50
    assert resolver_tramo_cobranza(121, TRAMOS_EXTERNO) == 0.00


def test_resolver_tramo_cobranza_dias_negativos_colapsa_al_tramo_minimo():
    """Auditoría 44, H-9: 12 filas históricas reales con banfec anterior a fecemi
    (mínimo -25 días). Un día negativo no debe caer fuera de todo tramo -- se trata
    como el tramo más favorable (<=21), igual que el ETL ya hace con el piso en 0."""
    assert resolver_tramo_cobranza(-25, TRAMOS_EXTERNO) == 2.0


def test_resolver_tramo_cobranza_sin_tramo_que_cubra_devuelve_cero():
    tramos_incompletos = [TramoCobranza(dias_hasta=21, tasa_pct=2.0)]
    assert resolver_tramo_cobranza(500, tramos_incompletos) == 0.0


def test_resolver_tramo_cobranza_sin_tope_superior():
    tramos_con_abierto = [TramoCobranza(dias_hasta=21, tasa_pct=2.0), TramoCobranza(dias_hasta=None, tasa_pct=0.25)]
    assert resolver_tramo_cobranza(9000, tramos_con_abierto) == 0.25


# ── calcular_comision_cobranza (verdad de campo VEN13, feb-2026) ────────────────
def test_calcular_comision_cobranza_reproduce_verdad_de_campo_ven13():
    cobros = [
        CobroComisionable(valor_cobrado=6381.44, dias_cobro=10),
        CobroComisionable(valor_cobrado=42320.79, dias_cobro=40),
        CobroComisionable(valor_cobrado=8867.37, dias_cobro=80),
        CobroComisionable(valor_cobrado=5650.03, dias_cobro=110),
    ]
    resultado = calcular_comision_cobranza(cobros, TRAMOS_EXTERNO)
    assert resultado.comision_total == pytest.approx(962.998, abs=0.01)
    assert resultado.total_cobrado == pytest.approx(63219.63, abs=0.01)
    assert len(resultado.desglose_tramos) == len(TRAMOS_EXTERNO)
    assert resultado.desglose_tramos[0].comision_tramo == pytest.approx(127.6288, abs=0.01)


def test_calcular_comision_cobranza_sin_cobros_es_cero():
    resultado = calcular_comision_cobranza([], TRAMOS_EXTERNO)
    assert resultado.comision_total == 0.0
    assert resultado.total_cobrado == 0.0


def test_calcular_comision_cobranza_excluye_dias_mayores_a_365_sin_tramo():
    cobros = [CobroComisionable(valor_cobrado=1000.0, dias_cobro=400)]
    resultado = calcular_comision_cobranza(cobros, TRAMOS_EXTERNO)
    assert resultado.comision_total == 0.0  # cae en el tramo 365 (tasa 0%)


# ── calcular_contado_agencia ─────────────────────────────────────────────────────
def test_calcular_contado_agencia_aplica_porcentaje():
    assert calcular_contado_agencia(10000.0, 1.0) == 100.0


def test_calcular_contado_agencia_negativo_no_produce_comision_negativa():
    assert calcular_contado_agencia(-500.0, 1.0) == 0.0


# ── evaluar_formula (tubería declarativa) ────────────────────────────────────────
def test_evaluar_formula_reproduce_la_formula_actual_legacy():
    """La fórmula 'actual' sembrada por la migración 0008 debe ser un no-op de
    comportamiento respecto al cálculo legacy: base * factor_tipo * multiplicador
    - devoluciones + bonos."""
    pasos = [
        PasoFormula(1, "base_lineas_venta", "sumar", 1000.0),
        PasoFormula(2, "factor_tipo_vendedor", "multiplicar", 0.7),
        PasoFormula(3, "multiplicador_cumplimiento", "multiplicar", 1.2),
        PasoFormula(4, "devoluciones", "restar", 20.0),
        PasoFormula(5, "bonos", "sumar", 15.0),
    ]
    resultado = evaluar_formula(pasos)
    assert resultado.comision_final == pytest.approx(1000 * 0.7 * 1.2 - 20 + 15)


def test_evaluar_formula_respeta_orden_no_el_orden_de_la_lista():
    pasos_desordenados = [
        PasoFormula(2, "b", "sumar", 5.0),
        PasoFormula(1, "a", "sumar", 10.0),
    ]
    resultado = evaluar_formula(pasos_desordenados)
    assert resultado.pasos[0]["componente"] == "a"
    assert resultado.pasos[1]["componente"] == "b"
    assert resultado.comision_final == 15.0


def test_evaluar_formula_piso_cero():
    pasos = [PasoFormula(1, "base_cobranza", "sumar", 100.0), PasoFormula(2, "devoluciones", "restar", 500.0)]
    assert evaluar_formula(pasos).comision_final == 0.0


def test_evaluar_formula_operador_no_soportado_lanza_error():
    with pytest.raises(ValueError):
        evaluar_formula([PasoFormula(1, "x", "dividir", 1.0)])
