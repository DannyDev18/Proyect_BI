# backend/tests/unit/test_goal_ml_service.py
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.core.exceptions import ExternalDataError, ModelContractError, ValidationError
from app.repositories.goal_repository import VendorMonthlySales, VendorTransactionFeatures
from app.services.goal_ml_service import GoalMLService


@pytest.fixture
def goal_repo():
    return MagicMock()


@pytest.fixture
def dataset_repo():
    return MagicMock()


@pytest.fixture
def goals_service():
    return MagicMock()


@pytest.fixture
def service(goal_repo, dataset_repo, goals_service):
    loader = MagicMock()
    loader.is_loaded.return_value = False  # sin modelos cargados salvo que un test lo cambie
    return GoalMLService(goal_repo, dataset_repo, loader, goals_service)


def _historial(n=12, base=1000.0):
    return [VendorMonthlySales(anio=2025, mes=m, ventas=base, unidades=10.0) for m in range(1, n + 1)]


def test_suggest_goal_lanza_validation_error_sin_historico(service, goal_repo):
    goal_repo.get_vendor_monthly_history.return_value = []
    with pytest.raises(ValidationError):
        service.suggest_goal("VEN01", "SUC1")


def test_suggest_goal_calcula_sin_senal_ml_si_anomaly_no_esta_cargado(service, goal_repo):
    goal_repo.get_vendor_monthly_history.return_value = _historial()
    goal_repo.get_latest_edw_period.return_value = None  # sin meta IA

    resultado = service.suggest_goal("VEN01", "SUC1")

    assert resultado.meta_sugerida_estadistica == pytest.approx(1000.0)
    assert resultado.meses_atipicos_ml_detectados == 0
    assert resultado.meta_sugerida_ia is None
    goal_repo.get_vendor_transactions_history.assert_not_called()


def test_detectar_meses_atipicos_continua_sin_senal_si_contrato_falla(service, goal_repo):
    loader = service.model_loader
    loader.is_loaded.return_value = True
    goal_repo.get_vendor_transactions_history.return_value = [
        VendorTransactionFeatures(anio=2025, mes=1, subtotal_neto=100.0, cantidad=1.0, costo_total=50.0, margen=50.0),
    ]

    with patch("app.services.goal_ml_service.inference.detect_anomalies", side_effect=ModelContractError("boom")):
        atipicos = service._detectar_meses_atipicos("VEN01", "SUC1", _historial(n=3))

    assert atipicos == frozenset()  # no bloquea el cálculo de meta, solo omite la señal


def test_detectar_meses_atipicos_devuelve_vacio_sin_transacciones(service, goal_repo):
    loader = service.model_loader
    loader.is_loaded.return_value = True
    goal_repo.get_vendor_transactions_history.return_value = []

    atipicos = service._detectar_meses_atipicos("VEN01", "SUC1", _historial(n=3))

    assert atipicos == frozenset()


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
