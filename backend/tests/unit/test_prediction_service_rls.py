# backend/tests/unit/test_prediction_service_rls.py
"""RLS de cartera para churn/recomendaciones/segmento (docs/auditoria/
34_actualizacion_modulo_ventas.md, H-V2): antes cualquier usuario `ventas` autenticado
podía consultar cualquier `cliente_id` del sistema, no solo los de su propia cartera.
Repositorios/ModelLoader 100% mockeados -- ningún test toca la BD ni carga modelos."""
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import PermissionDeniedError
from app.services.prediction_service import PredictionService


@pytest.fixture
def prediction_repo():
    repo = MagicMock()
    repo.get_churn_features.return_value = None  # degrada con gracia, no es lo que probamos aquí
    return repo


@pytest.fixture
def catalog_repo():
    repo = MagicMock()
    repo.cliente_pertenece_a_vendedor.return_value = True
    return repo


@pytest.fixture
def service(prediction_repo, catalog_repo):
    return PredictionService(prediction_repo, MagicMock(), MagicMock(), catalog_repo=catalog_repo)


def test_get_churn_risk_sin_restriccion_no_verifica_cartera(service, catalog_repo):
    """gerencia/administrador pasan codven_restriccion=None -- sin verificación."""
    service.get_churn_risk("CLI-999", codven_restriccion=None)
    catalog_repo.cliente_pertenece_a_vendedor.assert_not_called()


def test_get_churn_risk_con_restriccion_permite_cliente_propio(service, catalog_repo):
    catalog_repo.cliente_pertenece_a_vendedor.return_value = True
    service.get_churn_risk("CLI-001", codven_restriccion="V001")
    catalog_repo.cliente_pertenece_a_vendedor.assert_called_once_with("CLI-001", "V001")


def test_get_churn_risk_rechaza_cliente_ajeno(service, catalog_repo):
    catalog_repo.cliente_pertenece_a_vendedor.return_value = False
    with pytest.raises(PermissionDeniedError):
        service.get_churn_risk("CLI-999", codven_restriccion="V001")


def test_get_product_recommendations_rechaza_cliente_ajeno(service, catalog_repo, prediction_repo):
    catalog_repo.cliente_pertenece_a_vendedor.return_value = False
    with pytest.raises(PermissionDeniedError):
        service.get_product_recommendations("CLI-999", codven_restriccion="V001")
    prediction_repo.get_client_purchase_history.assert_not_called()


def test_get_customer_segment_rechaza_cliente_ajeno(service, catalog_repo, prediction_repo):
    catalog_repo.cliente_pertenece_a_vendedor.return_value = False
    with pytest.raises(PermissionDeniedError):
        service.get_customer_segment("CLI-999", codven_restriccion="V001")
    prediction_repo.get_rfm_features.assert_not_called()


def test_get_churn_risk_batch_respeta_umbral_configurable(service, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "CHURN_UMBRAL_RIESGO_ALTO", 0.9)

    import pandas as pd
    df = pd.DataFrame({
        "cliente_id": ["CLI-001"], "frequency": [1], "monetary_value": [100.0], "average_ticket": [100.0],
    })
    service.prediction_repo.get_churn_features_batch.return_value = df

    from unittest.mock import patch
    with patch("app.services.prediction_service.inference.predict_churn") as mock_predict:
        mock_predict.return_value = pd.DataFrame({"churn_probability": [0.7]})  # 70%: alto con umbral 0.5, no con 0.9
        resultado = service.get_churn_risk_batch(["CLI-001"])

    assert resultado["CLI-001"]["riesgo_alto"] is False
