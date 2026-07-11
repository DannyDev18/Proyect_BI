# backend/tests/unit/test_commission_service.py
import datetime
from unittest.mock import MagicMock

import pytest

from app.services.commission_service import CommissionService


@pytest.fixture
def goal_repo():
    return MagicMock()


@pytest.fixture
def service(goal_repo):
    return CommissionService(goal_repo)


def test_get_commission_tracking_calcula_comision_por_fila(service, goal_repo):
    goal_repo.get_commission_tracking_rows.return_value = [
        {
            "id": 1, "id_vendedor_origen": "VEN01", "vendedor": "Juan Pérez",
            "monto_meta": 10000.0, "comision_base_pct": 7.0, "bono_sobrecumplimiento": 500.0,
            "estado": "APROBADA", "venta_neta": 12000.0,
        },
        {
            "id": 2, "id_vendedor_origen": "VEN02", "vendedor": "Ana Ruiz",
            "monto_meta": 10000.0, "comision_base_pct": 7.0, "bono_sobrecumplimiento": 500.0,
            "estado": "APROBADA", "venta_neta": 5000.0,
        },
    ]

    filas = service.get_commission_tracking(anio=2026, mes=6)

    assert len(filas) == 2
    assert filas[0].nivel == "EXCELENTE"
    assert filas[0].comision_devengada == pytest.approx(12000.0 * 0.09 + 500.0)
    assert filas[1].nivel == "LEJOS"
    assert filas[1].comision_devengada == 0.0


def test_get_my_commission_sin_meta_configurada_devuelve_ceros(service, goal_repo):
    goal_repo.get_goal_for_period.return_value = None
    goal_repo.get_vendor_net_sales_period.return_value = 5000.0

    resultado = service.get_my_commission("VEN01", 2026, 6)

    assert resultado.monto_meta == 0.0
    assert resultado.comision_devengada == 0.0
    assert resultado.nivel == "LEJOS"


def test_get_my_commission_usa_meta_y_venta_real(service, goal_repo):
    goal = MagicMock(monto_meta=10000.0, comision_base_pct=7.0, bono_sobrecumplimiento=500.0)
    goal_repo.get_goal_for_period.return_value = goal
    goal_repo.get_vendor_net_sales_period.return_value = 9500.0

    resultado = service.get_my_commission("VEN01", 2026, 6)

    assert resultado.venta_real == 9500.0
    assert resultado.nivel == "META"
    assert resultado.comision_devengada == pytest.approx(9500.0 * 0.07)


def test_get_my_commission_mensaje_meta_superada(service, goal_repo):
    goal = MagicMock(monto_meta=10000.0, comision_base_pct=7.0, bono_sobrecumplimiento=500.0)
    goal_repo.get_goal_for_period.return_value = goal
    goal_repo.get_vendor_net_sales_period.return_value = 11000.0

    resultado = service.get_my_commission("VEN01", 2026, 6)

    assert resultado.mensaje_alerta == "¡Meta superada este período!"
    assert resultado.en_alerta_cierre is False


def test_get_my_commission_periodo_cerrado_no_tiene_dias_restantes(service, goal_repo):
    """Un período distinto al mes/año actuales (histórico) no debe reportar días
    restantes ni disparar la alerta de última semana."""
    goal = MagicMock(monto_meta=10000.0, comision_base_pct=7.0, bono_sobrecumplimiento=500.0)
    goal_repo.get_goal_for_period.return_value = goal
    goal_repo.get_vendor_net_sales_period.return_value = 2000.0

    resultado = service.get_my_commission("VEN01", 2020, 1)

    assert resultado.dias_restantes_mes == 0
    assert resultado.en_alerta_cierre is False


def test_get_my_commission_alerta_ultima_semana_bajo_umbral(service, goal_repo, monkeypatch):
    """Fuerza 'hoy' a los últimos días del mes en curso con bajo cumplimiento -> alerta."""
    hoy_real = datetime.date.today()
    ultimo_dia = datetime.date(hoy_real.year + (hoy_real.month == 12), (hoy_real.month % 12) + 1, 1) - datetime.timedelta(days=1)

    class _FakeDate(datetime.date):
        @classmethod
        def today(cls):
            return ultimo_dia

    monkeypatch.setattr("app.services.commission_service.datetime.date", _FakeDate)

    goal = MagicMock(monto_meta=10000.0, comision_base_pct=7.0, bono_sobrecumplimiento=500.0)
    goal_repo.get_goal_for_period.return_value = goal
    goal_repo.get_vendor_net_sales_period.return_value = 1000.0  # 10% cumplimiento

    resultado = service.get_my_commission("VEN01", ultimo_dia.year, ultimo_dia.month)

    assert resultado.en_alerta_cierre is True
    assert resultado.mensaje_alerta is not None
    assert "Última semana" in resultado.mensaje_alerta


def test_get_post_goal_invoices_vacio_sin_meta(service, goal_repo):
    goal_repo.get_goal_for_period.return_value = None
    assert service.get_post_goal_invoices("VEN01", 2026, 6) == []


def test_get_post_goal_invoices_delega_al_repositorio(service, goal_repo):
    goal = MagicMock(monto_meta=10000.0)
    goal_repo.get_goal_for_period.return_value = goal
    goal_repo.get_post_goal_invoices.return_value = [
        {"num_factura": "F001", "fecha": "2026-06-15", "monto_factura": 3000.0, "acumulado_venta": 10500.0},
    ]

    facturas = service.get_post_goal_invoices("VEN01", 2026, 6)

    assert len(facturas) == 1
    assert facturas[0].num_factura == "F001"
    goal_repo.get_post_goal_invoices.assert_called_once_with("VEN01", 2026, 6, 10000.0)
