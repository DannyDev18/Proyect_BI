# backend/tests/unit/test_goal_ml_service.py
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.core.exceptions import ExternalDataError, ModelContractError, ValidationError
from app.repositories.goal_repository import VendorMonthlySales, VendorRecentSales, VendorTransactionFeatures
from app.services.goal_ml_service import GoalMLService


@pytest.fixture
def goal_repo():
    return MagicMock()


@pytest.fixture
def dataset_repo():
    return MagicMock()


@pytest.fixture
def service(goal_repo, dataset_repo):
    loader = MagicMock()
    loader.is_loaded.return_value = False  # sin modelos cargados salvo que un test lo cambie
    return GoalMLService(goal_repo, dataset_repo, loader)


def _historial(n=12, base=1000.0):
    return [VendorMonthlySales(anio=2025, mes=m, ventas=base, unidades=10.0) for m in range(1, n + 1)]


def test_suggest_goal_lanza_validation_error_sin_historico(service, goal_repo):
    goal_repo.get_vendor_monthly_history.return_value = []
    with pytest.raises(ValidationError):
        service.suggest_goal("VEN01")


def test_suggest_goal_calcula_sin_senal_ml_si_anomaly_no_esta_cargado(service, goal_repo):
    goal_repo.get_vendor_monthly_history.return_value = _historial()

    resultado = service.suggest_goal("VEN01")

    assert resultado.meta_sugerida_estadistica == pytest.approx(1000.0)
    assert resultado.meses_atipicos_ml_detectados == 0
    goal_repo.get_vendor_transactions_history.assert_not_called()


def test_detectar_meses_atipicos_continua_sin_senal_si_contrato_falla(service, goal_repo):
    loader = service.model_loader
    loader.is_loaded.return_value = True
    goal_repo.get_vendor_transactions_history.return_value = [
        VendorTransactionFeatures(anio=2025, mes=1, subtotal_neto=100.0, cantidad=1.0, costo_total=50.0, margen=50.0),
    ]

    with patch("app.services.goal_ml_service.inference.detect_anomalies", side_effect=ModelContractError("boom")):
        atipicos = service._detectar_meses_atipicos("VEN01", _historial(n=3))

    assert atipicos == frozenset()  # no bloquea el cálculo de meta, solo omite la señal


def test_detectar_meses_atipicos_devuelve_vacio_sin_transacciones(service, goal_repo):
    loader = service.model_loader
    loader.is_loaded.return_value = True
    goal_repo.get_vendor_transactions_history.return_value = []

    atipicos = service._detectar_meses_atipicos("VEN01", _historial(n=3))

    assert atipicos == frozenset()


# ── Generación OFICIAL de metas (docs/auditoria/19_/20_...md): grano vendedor, IQR puro ──
def _vendor(vendedor: str, unidades_anterior: float = 20.0) -> VendorRecentSales:
    return VendorRecentSales(vendedor_origen=vendedor, unidades_anterior=unidades_anterior)


def test_generate_proposals_una_fila_por_vendedor_sin_sucursal(service, goal_repo):
    """Antes de la corrección, la consulta de tendencias traía una fila por
    vendedor×sucursal y se insertaba una meta por cada una -- duplicando registros para
    un mismo vendedor. Ahora es una fila por vendedor (docs/auditoria/19_...md)."""
    goal_repo.get_vendors_with_recent_sales.return_value = [_vendor("VEN01"), _vendor("VEN02")]
    goal_repo.get_vendor_monthly_history.return_value = _historial()
    goal_repo.find_proposal.return_value = None

    creados = service.generate_proposals(anio=2026, mes=7, factor_presion=1.1)

    assert creados == 2
    assert goal_repo.insert_proposal.call_count == 2
    inserted_vendedores = {call.args[2] for call in goal_repo.insert_proposal.call_args_list}
    assert inserted_vendedores == {"VEN01", "VEN02"}


def test_generate_proposals_actualiza_propuesta_existente_sin_tocar_aprobada(service, goal_repo):
    goal_repo.get_vendors_with_recent_sales.return_value = [_vendor("VEN01")]
    goal_repo.get_vendor_monthly_history.return_value = _historial()
    goal_repo.find_proposal.return_value = (7, "APROBADA")

    creados = service.generate_proposals(anio=2026, mes=7)

    assert creados == 0
    goal_repo.insert_proposal.assert_not_called()
    goal_repo.update_proposal_amounts.assert_not_called()


def test_forecast_cierre_propaga_external_data_error_si_falla_el_repo(service, dataset_repo):
    dataset_repo.get_daily_sales_history.side_effect = RuntimeError("db caida")
    with pytest.raises(ExternalDataError):
        service.forecast_cierre(sucursal="SUC1", meta_mensual=1000.0)


def test_forecast_cierre_devuelve_cero_con_historial_vacio(service, dataset_repo):
    dataset_repo.get_daily_sales_history.return_value = pd.DataFrame(columns=["ds", "y_sales_net"])
    resultado = service.forecast_cierre(sucursal="SUC1", meta_mensual=1000.0)
    assert resultado.proyeccion_cierre == 0.0
    assert resultado.probabilidad_alcanzar_meta is None


def test_get_commercial_recommendations_vacio_sin_top_productos(service, goal_repo):
    goal_repo.get_vendor_top_products.return_value = []
    assert service.get_commercial_recommendations("VEN01") == []


def test_classify_vendor_risk_marca_en_riesgo_y_alta_probabilidad(service):
    ranking = [
        {"nombre": "A", "ventas": 90000.0, "meta": 100000.0, "cumple": False},
        {"nombre": "B", "ventas": 100.0, "meta": 100000.0, "cumple": False},
    ]
    resultado = service.classify_vendor_risk(ranking)
    estados = {r.nombre: r.estado for r in resultado}
    assert estados["A"] == "alta_probabilidad"
    assert estados["B"] == "en_riesgo"


def test_classify_vendor_risk_maneja_meta_cero(service):
    resultado = service.classify_vendor_risk([{"nombre": "Z", "ventas": 500.0, "meta": 0.0, "cumple": False}])
    assert resultado[0].pct_cumplimiento == 0.0


def test_probabilidad_alcanzar_meta_none_sin_mae():
    assert GoalMLService._probabilidad_alcanzar_meta(1000.0, 900.0, None, 5) is None


def test_probabilidad_alcanzar_meta_alta_si_proyeccion_supera_meta_con_margen():
    prob = GoalMLService._probabilidad_alcanzar_meta(2000.0, 900.0, mae_modelo=50.0, dias_restantes=5)
    assert prob is not None and prob > 90.0


def test_probabilidad_alcanzar_meta_baja_si_proyeccion_muy_por_debajo():
    prob = GoalMLService._probabilidad_alcanzar_meta(100.0, 900.0, mae_modelo=50.0, dias_restantes=5)
    assert prob is not None and prob < 10.0
