# backend/tests/unit/test_commission_service.py
import datetime
from unittest.mock import MagicMock

import pytest

from app.core.config import settings
from app.services.commission_engine import ComisionVariableCalculada, NivelCumplimiento
from app.services.commission_service import CommissionService


@pytest.fixture
def goal_repo():
    return MagicMock()


@pytest.fixture
def service(goal_repo):
    return CommissionService(goal_repo)


def _cv_dummy(comision_final: float = 100.0) -> ComisionVariableCalculada:
    return ComisionVariableCalculada(
        comision_base=comision_final, comision_post_tipo=comision_final,
        nivel=NivelCumplimiento.META, multiplicador_cumplimiento=1.0,
        comision_post_cumplimiento=comision_final, devoluciones_estimadas=0.0,
        bonos_total=0.0, comision_final=comision_final, desglose_lineas=(),
    )


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


# ══════════════════════════════════════════════════════════════════════════════
# Snapshot de liquidación: mapeo de `settings.COMISION_MODO` -> `modo` de la BD
# (auditoría 34, H-4). `comision_liquidaciones.modo` tiene un CHECK ('sombra','oficial'),
# distinto del vocabulario del backend ('plana'/'sombra'/'variable') -- pasar el valor
# de `COMISION_MODO` tal cual violaba el CHECK en modo "variable".
# ══════════════════════════════════════════════════════════════════════════════
@pytest.fixture
def commission_config_repo():
    repo = MagicMock()
    repo.get_matriz_as_reglas.return_value = []
    repo.get_factores_credito_as_rangos.return_value = []
    repo.get_config_vendedor.return_value = None
    repo.get_liquidacion.return_value = None  # sin snapshot congelado previo por defecto
    return repo


@pytest.fixture
def service_variable(goal_repo, commission_config_repo):
    return CommissionService(goal_repo, commission_config_repo)


def test_snapshot_modo_variable_se_persiste_como_oficial(service_variable, goal_repo, commission_config_repo, monkeypatch):
    monkeypatch.setattr(settings, "COMISION_MODO", "variable")
    goal_repo.get_commission_lines.return_value = []
    goal_repo.get_vendor_devoluciones_period.return_value = 0.0
    goal_repo.get_cross_sell_accepted_amount.return_value = 0.0
    goal_repo.get_new_or_reactivated_clients.return_value = 0
    goal_repo.get_vendor_credit_profile.return_value = {"dias_cobro_promedio": None}
    goal_repo.get_goal_for_period.return_value = MagicMock(monto_meta=10000.0, comision_base_pct=7.0, bono_sobrecumplimiento=0.0)
    goal_repo.get_vendor_net_sales_period.return_value = 9000.0

    service_variable.get_my_commission("VEN01", 2020, 1)  # período cerrado -> persiste snapshot

    commission_config_repo.save_liquidacion.assert_called_once()
    kwargs = commission_config_repo.save_liquidacion.call_args.kwargs
    assert kwargs["modo"] == "oficial"


def test_snapshot_modo_sombra_se_persiste_igual(service_variable, goal_repo, commission_config_repo, monkeypatch):
    monkeypatch.setattr(settings, "COMISION_MODO", "sombra")
    goal_repo.get_commission_lines.return_value = []
    goal_repo.get_vendor_devoluciones_period.return_value = 0.0
    goal_repo.get_cross_sell_accepted_amount.return_value = 0.0
    goal_repo.get_new_or_reactivated_clients.return_value = 0
    goal_repo.get_vendor_credit_profile.return_value = {"dias_cobro_promedio": None}
    goal_repo.get_goal_for_period.return_value = MagicMock(monto_meta=10000.0, comision_base_pct=7.0, bono_sobrecumplimiento=0.0)
    goal_repo.get_vendor_net_sales_period.return_value = 9000.0

    service_variable.get_my_commission("VEN01", 2020, 1)

    kwargs = commission_config_repo.save_liquidacion.call_args.kwargs
    assert kwargs["modo"] == "sombra"


def test_snapshot_no_se_persiste_en_modo_plana(service_variable, goal_repo, commission_config_repo, monkeypatch):
    monkeypatch.setattr(settings, "COMISION_MODO", "plana")
    goal_repo.get_goal_for_period.return_value = MagicMock(monto_meta=10000.0, comision_base_pct=7.0, bono_sobrecumplimiento=0.0)
    goal_repo.get_vendor_net_sales_period.return_value = 9000.0

    resultado = service_variable.get_my_commission("VEN01", 2020, 1)

    assert resultado.comision_variable is None
    commission_config_repo.save_liquidacion.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
# H1/H2 (docs/auditoria/35_actualizacion_modulo_metas.md): configuración vigente al
# CIERRE del período (no "hoy") + inmutabilidad real de liquidaciones oficiales.
# ══════════════════════════════════════════════════════════════════════════════
def test_calculo_variable_resuelve_config_vigente_al_cierre_del_periodo(service_variable, goal_repo, commission_config_repo, monkeypatch):
    monkeypatch.setattr(settings, "COMISION_MODO", "sombra")  # no se congela -> siempre recalcula
    goal_repo.get_commission_lines.return_value = []
    goal_repo.get_vendor_devoluciones_period.return_value = 0.0
    goal_repo.get_cross_sell_accepted_amount.return_value = 0.0
    goal_repo.get_new_or_reactivated_clients.return_value = 0
    goal_repo.get_vendor_credit_profile.return_value = {"dias_cobro_promedio": None}
    goal_repo.get_goal_for_period.return_value = MagicMock(monto_meta=10000.0, comision_base_pct=7.0, bono_sobrecumplimiento=0.0)
    goal_repo.get_vendor_net_sales_period.return_value = 9000.0

    service_variable.get_my_commission("VEN01", 2026, 3)  # período cerrado (hoy > marzo 2026)

    fecha_usada_matriz = commission_config_repo.get_matriz_as_reglas.call_args.args[0]
    fecha_usada_credito = commission_config_repo.get_factores_credito_as_rangos.call_args.args[0]
    assert fecha_usada_matriz == datetime.date(2026, 3, 31)
    assert fecha_usada_credito == datetime.date(2026, 3, 31)


def test_liquidacion_oficial_congelada_no_se_recalcula_ni_se_reescribe(service_variable, goal_repo, commission_config_repo, monkeypatch):
    """H2: una vez que existe un snapshot 'oficial' para el período, debe devolverse
    tal cual -- ni se recalcula con la config actual ni se vuelve a escribir."""
    monkeypatch.setattr(settings, "COMISION_MODO", "variable")
    snapshot = MagicMock()
    snapshot.detalle_json = {
        "comision_base": 100.0, "comision_post_tipo": 100.0, "nivel": "META",
        "multiplicador_cumplimiento": 1.0, "comision_post_cumplimiento": 100.0,
        "devoluciones_estimadas": 0.0, "bonos_total": 0.0, "comision_final": 555.55,
        "desglose_lineas": [],
    }
    commission_config_repo.get_liquidacion.return_value = snapshot
    goal_repo.get_goal_for_period.return_value = MagicMock(monto_meta=10000.0, comision_base_pct=7.0, bono_sobrecumplimiento=0.0)
    goal_repo.get_vendor_net_sales_period.return_value = 9000.0

    resultado = service_variable.get_my_commission("VEN01", 2020, 1)

    assert resultado.comision_variable == 555.55
    assert resultado.nivel_variable == "META"
    commission_config_repo.get_matriz_as_reglas.assert_not_called()
    commission_config_repo.save_liquidacion.assert_not_called()
    goal_repo.get_commission_lines.assert_not_called()


def test_liquidacion_sombra_sigue_recalculando_aunque_exista_snapshot_previo(service_variable, goal_repo, commission_config_repo, monkeypatch):
    """El modo 'sombra' (piloto, no paga) debe seguir refrescándose en cada consulta
    -- la inmutabilidad de H2 solo aplica al modo 'oficial'."""
    monkeypatch.setattr(settings, "COMISION_MODO", "sombra")
    commission_config_repo.get_liquidacion.return_value = MagicMock(detalle_json={
        "comision_base": 1.0, "comision_post_tipo": 1.0, "nivel": "LEJOS",
        "multiplicador_cumplimiento": 0.0, "comision_post_cumplimiento": 0.0,
        "devoluciones_estimadas": 0.0, "bonos_total": 0.0, "comision_final": 1.0,
        "desglose_lineas": [],
    })
    goal_repo.get_commission_lines.return_value = []
    goal_repo.get_vendor_devoluciones_period.return_value = 0.0
    goal_repo.get_cross_sell_accepted_amount.return_value = 0.0
    goal_repo.get_new_or_reactivated_clients.return_value = 0
    goal_repo.get_vendor_credit_profile.return_value = {"dias_cobro_promedio": None}
    goal_repo.get_goal_for_period.return_value = MagicMock(monto_meta=10000.0, comision_base_pct=7.0, bono_sobrecumplimiento=0.0)
    goal_repo.get_vendor_net_sales_period.return_value = 9000.0

    service_variable.get_my_commission("VEN01", 2020, 1)

    goal_repo.get_commission_lines.assert_called_once()
    commission_config_repo.save_liquidacion.assert_called_once()


def test_snapshot_no_se_persiste_en_mes_en_curso(service_variable, goal_repo, commission_config_repo, monkeypatch):
    """Salvaguarda 6 existente: el mes en curso no se congela porque su cálculo cambia
    con cada consulta -- confirmamos que sigue vigente tras el fix de H-4."""
    monkeypatch.setattr(settings, "COMISION_MODO", "variable")
    hoy = datetime.date.today()
    goal_repo.get_commission_lines.return_value = []
    goal_repo.get_vendor_devoluciones_period.return_value = 0.0
    goal_repo.get_cross_sell_accepted_amount.return_value = 0.0
    goal_repo.get_new_or_reactivated_clients.return_value = 0
    goal_repo.get_vendor_credit_profile.return_value = {"dias_cobro_promedio": None}
    goal_repo.get_goal_for_period.return_value = MagicMock(monto_meta=10000.0, comision_base_pct=7.0, bono_sobrecumplimiento=0.0)
    goal_repo.get_vendor_net_sales_period.return_value = 9000.0

    service_variable.get_my_commission("VEN01", hoy.year, hoy.month)

    commission_config_repo.save_liquidacion.assert_not_called()
