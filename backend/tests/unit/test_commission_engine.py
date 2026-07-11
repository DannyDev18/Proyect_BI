# backend/tests/unit/test_commission_engine.py
import pytest

from app.services.commission_engine import NivelCumplimiento, calcular_comision, calcular_nivel


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
