# backend/tests/unit/test_commission_variable_engine.py
"""Corrección de diseño 2026-07-30 (auditoría 44, petición explícita del usuario):
las Comisiones Variables son UN SOLO TOTAL por vendedor -- líneas de venta (margen/
categoría) + cobranza (por tramo de días de cobro) + ventas de contado de agencia se
SUMAN, nunca se elige entre "un esquema u otro". Estos tests verifican que
`calcular_comision_variable_completa` combina TODOS los componentes activos de la
fórmula (hay una sola) en una única comisión final."""
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.services.commission_engine import TramoCumplimiento
from app.services.commission_variable_engine import calcular_comision_variable_completa


@dataclass
class _Componente:
    orden: int
    componente: str
    operador: str
    activo: bool
    parametros: dict[str, Any]


FORMULA_UNIFICADA = [
    _Componente(1, "base_lineas_venta", "sumar", True, {}),
    _Componente(2, "base_cobranza", "sumar", True, {}),
    _Componente(3, "contado_agencia", "sumar", True, {}),
    _Componente(4, "factor_tipo_vendedor", "multiplicar", True, {}),
    _Componente(5, "multiplicador_cumplimiento", "multiplicar", True, {}),
    _Componente(6, "devoluciones", "restar", True, {}),
    _Componente(7, "bonos", "sumar", True, {}),
]


@pytest.fixture
def goal_repo():
    repo = MagicMock()
    repo.get_commission_lines.return_value = []  # sin líneas -> base_lineas_venta = 0
    repo.get_cobros_periodo.return_value = []  # sin cobros -> base_cobranza = 0
    repo.get_vendor_devoluciones_period.return_value = 0.0
    repo.get_cross_sell_accepted_amount.return_value = 0.0
    repo.get_new_or_reactivated_clients.return_value = 0
    repo.get_vendor_credit_profile.return_value = {"dias_cobro_promedio": None}
    return repo


@pytest.fixture
def commission_config_repo():
    repo = MagicMock()
    repo.get_formula_activa.return_value = (MagicMock(clave="unica"), FORMULA_UNIFICADA)
    repo.get_matriz_as_reglas.return_value = []
    repo.get_factores_credito_as_rangos.return_value = []
    repo.get_config_vendedor.return_value = None
    repo.get_tramos_cobranza_as_rangos.return_value = []
    # Auditoría 45: sin tramos configurados, cae al fallback defensivo
    # (`TRAMOS_CUMPLIMIENTO_FALLBACK`) -- estos tests preexistentes no ejercitan la
    # escala de sobrecumplimiento nueva, solo necesitan que el motor no reviente.
    repo.get_tramos_cumplimiento_as_tramos.return_value = []
    return repo


def test_suma_base_cobranza_a_la_comision_aunque_no_haya_lineas_de_venta(goal_repo, commission_config_repo):
    """Caso central del pedido del usuario: un vendedor sin líneas de venta comisionables
    en el mes pero con cobros reales debe recibir comisión (antes de esta corrección, si
    la fórmula "cobranza" no estaba activa, este dinero simplemente no se pagaba)."""
    cobro = MagicMock(valor_cobrado=1000.0, dias_cobro=10)
    goal_repo.get_cobros_periodo.return_value = [cobro]
    commission_config_repo.get_tramos_cobranza_as_rangos.return_value = [
        MagicMock(dias_hasta=21, tasa_pct=2.0),
    ]

    import datetime
    # monto_meta=venta_real -> nivel META, multiplicador 1.0 (no se anula por
    # COMISION_PISO_LEJOS cuando no hay meta configurada).
    resultado = calcular_comision_variable_completa(
        goal_repo=goal_repo, commission_config_repo=commission_config_repo,
        vendedor_origen="VEN01", anio=2026, mes=2, venta_real=1000.0, monto_meta=1000.0,
        fecha_config=datetime.date(2026, 2, 28),
    )
    assert resultado.montos["base_cobranza"] == pytest.approx(20.0)  # 1000 * 2%
    assert resultado.comision_final > 0.0


def test_lineas_de_venta_y_cobranza_se_suman_en_una_sola_comision(goal_repo, commission_config_repo):
    """El requisito explícito: NO es "margen/categoría" O "cobranza" -- es la SUMA de
    ambas, multiplicada por el factor de tipo y el cumplimiento, igual que si fuera un
    solo flujo de ingresos del vendedor."""
    import datetime
    linea = MagicMock(
        codart="A1", clase="B", subclase=None, es_servicio=False,
        subtotal_neto=1000.0, margen_bruto=1000.0, valor_descuento=0.0, dias_plazo=0,
    )
    goal_repo.get_commission_lines.return_value = [linea]
    cobro = MagicMock(valor_cobrado=1000.0, dias_cobro=10)
    goal_repo.get_cobros_periodo.return_value = [cobro]
    commission_config_repo.get_tramos_cobranza_as_rangos.return_value = [
        MagicMock(dias_hasta=21, tasa_pct=2.0),
    ]

    resultado = calcular_comision_variable_completa(
        goal_repo=goal_repo, commission_config_repo=commission_config_repo,
        vendedor_origen="VEN01", anio=2026, mes=2, venta_real=0.0, monto_meta=0.0,
        fecha_config=datetime.date(2026, 2, 28),
    )
    # base_lineas_venta (grupo default C, tasa 5% sobre margen -- ver
    # ConfigComisionVariable.tasa_default_pct) = 1000 * 0.05 = 50.0
    # base_cobranza = 1000 * 0.02 = 20.0
    # Sin meta (monto_meta=0) -> nivel LEJOS -> multiplicador = COMISION_PISO_LEJOS
    assert resultado.montos["base_lineas_venta"] == pytest.approx(50.0, abs=0.01)
    assert resultado.montos["base_cobranza"] == pytest.approx(20.0, abs=0.01)


def test_formula_fallback_sin_configuracion_reproduce_estructura_legacy(goal_repo, commission_config_repo):
    """Sin ninguna fórmula activa en la BD (dato borrado a mano), el motor no debe
    dejar al vendedor sin comisión -- cae al fallback defensivo (líneas de venta ×
    tipo × cumplimiento − devoluciones + bonos)."""
    import datetime
    commission_config_repo.get_formula_activa.return_value = None
    linea = MagicMock(
        codart="A1", clase="B", subclase=None, es_servicio=False,
        subtotal_neto=1000.0, margen_bruto=1000.0, valor_descuento=0.0, dias_plazo=0,
    )
    goal_repo.get_commission_lines.return_value = [linea]

    resultado = calcular_comision_variable_completa(
        goal_repo=goal_repo, commission_config_repo=commission_config_repo,
        vendedor_origen="VEN01", anio=2026, mes=2, venta_real=1000.0, monto_meta=1000.0,
        fecha_config=datetime.date(2026, 2, 28),
    )
    assert "base_cobranza" not in resultado.montos
    assert "contado_agencia" not in resultado.montos
    assert resultado.montos["base_lineas_venta"] == pytest.approx(50.0, abs=0.01)


# ══════════════════════════════════════════════════════════════════════════════
# Auditoría 45 (docs/features/plan_comisiones_sobrecumplimiento_umbral_y_desglose.md):
# umbral mínimo de pago al 90% -- un vendedor bajo el umbral debe recibir $0 en el
# multiplicador de cumplimiento aunque sus bases (líneas/cobranza) sean positivas.
# ══════════════════════════════════════════════════════════════════════════════
TRAMOS_R3 = [
    TramoCumplimiento(0.0, 90.0, 0.0, "Sin comisión (< 90% de la meta)"),
    TramoCumplimiento(90.0, 100.0, 1.0, "Meta"),
    TramoCumplimiento(100.0, 110.0, 1.2, "Sobrecumplimiento"),
    TramoCumplimiento(110.0, 125.0, 1.35, "Sobrecumplimiento alto"),
    TramoCumplimiento(125.0, None, 1.5, "Excelencia"),
]


def test_umbral_90_deja_comision_en_cero_pese_a_bases_positivas(goal_repo, commission_config_repo):
    """R-3 del plan: un vendedor al 85% de su meta (tramo CERCA histórico, 0.7x) debe
    quedar en $0 -- no en el 70% de la comisión que pagaba antes de la auditoría 45."""
    linea = MagicMock(
        codart="A1", clase="B", subclase=None, es_servicio=False,
        subtotal_neto=1000.0, margen_bruto=1000.0, valor_descuento=0.0, dias_plazo=0,
    )
    goal_repo.get_commission_lines.return_value = [linea]
    cobro = MagicMock(valor_cobrado=1000.0, dias_cobro=10)
    goal_repo.get_cobros_periodo.return_value = [cobro]
    commission_config_repo.get_tramos_cobranza_as_rangos.return_value = [MagicMock(dias_hasta=21, tasa_pct=2.0)]

    import datetime
    resultado = calcular_comision_variable_completa(
        goal_repo=goal_repo, commission_config_repo=commission_config_repo,
        vendedor_origen="VEN01", anio=2026, mes=2, venta_real=850.0, monto_meta=1000.0,
        fecha_config=datetime.date(2026, 2, 28), tramos_cumplimiento=TRAMOS_R3,
        aplicar_ajuste_meta_por_tipo=False,  # aísla el % de cumplimiento del ajuste por tipo de vendedor
    )
    assert resultado.montos["base_lineas_venta"] > 0.0
    assert resultado.montos["base_cobranza"] > 0.0
    assert resultado.montos["multiplicador_cumplimiento"] == 0.0
    assert resultado.comision_final == 0.0
    assert resultado.tramo is not None and resultado.tramo.etiqueta == "Sin comisión (< 90% de la meta)"
    assert resultado.pct_cumplimiento == pytest.approx(85.0)


def test_umbral_90_deja_la_traza_consistente_con_el_cero_pese_a_bonos(goal_repo, commission_config_repo):
    """Bug real encontrado en vivo (auditoría 47, continuación de la Fase 2): la
    compuerta forzaba `comision_final=0.0` pero dejaba la traza (`traza_formula`, el
    desglose que ve gerencia) mostrando `devoluciones`/`bonos` restando/sumando sobre el
    acumulado SIN la compuerta, terminando en un `acumulado_tras_paso` final distinto de
    cero -- gerencia veía un desglose que sumaba a varios miles de dólares pese a que la
    comisión real era $0. Desde el paso `multiplicador_cumplimiento` en adelante, la
    traza debe quedar en $0, igual que `comision_final`."""
    linea = MagicMock(
        codart="A1", clase="B", subclase=None, es_servicio=False,
        subtotal_neto=1000.0, margen_bruto=1000.0, valor_descuento=0.0, dias_plazo=0,
    )
    goal_repo.get_commission_lines.return_value = [linea]
    goal_repo.get_new_or_reactivated_clients.return_value = 10  # bono de cliente nuevo > 0

    import datetime
    resultado = calcular_comision_variable_completa(
        goal_repo=goal_repo, commission_config_repo=commission_config_repo,
        vendedor_origen="VEN01", anio=2026, mes=2, venta_real=850.0, monto_meta=1000.0,
        fecha_config=datetime.date(2026, 2, 28), tramos_cumplimiento=TRAMOS_R3,
        aplicar_ajuste_meta_por_tipo=False,
    )
    assert resultado.montos["bonos"] > 0.0
    assert resultado.comision_final == 0.0

    compuerta_alcanzada = False
    for paso in resultado.traza_formula:
        if paso["componente"] == "multiplicador_cumplimiento":
            compuerta_alcanzada = True
        if compuerta_alcanzada:
            assert paso["acumulado_tras_paso"] == 0.0, f"paso {paso['componente']} debería quedar en $0 tras la compuerta"


def test_sobrecumplimiento_escala_por_encima_de_100(goal_repo, commission_config_repo):
    """R-1 del plan: un vendedor muy por encima de la meta (130%) recibe la escala
    (1.5x en 'Excelencia'), no el escalón plano único de 1.2x."""
    linea = MagicMock(
        codart="A1", clase="B", subclase=None, es_servicio=False,
        subtotal_neto=1000.0, margen_bruto=1000.0, valor_descuento=0.0, dias_plazo=0,
    )
    goal_repo.get_commission_lines.return_value = [linea]

    import datetime
    resultado = calcular_comision_variable_completa(
        goal_repo=goal_repo, commission_config_repo=commission_config_repo,
        vendedor_origen="VEN01", anio=2026, mes=2, venta_real=1300.0, monto_meta=1000.0,
        fecha_config=datetime.date(2026, 2, 28), tramos_cumplimiento=TRAMOS_R3,
        aplicar_ajuste_meta_por_tipo=False,
    )
    assert resultado.montos["multiplicador_cumplimiento"] == 1.5
    assert resultado.tramo is not None and resultado.tramo.etiqueta == "Excelencia"
