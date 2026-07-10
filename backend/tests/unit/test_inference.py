# backend/tests/unit/test_inference.py
"""Prueba las funciones puras de `app/ml/inference.py` con un ModelLoader fake
(modelo dummy) -- no requiere los .pkl reales."""
import pandas as pd
import pytest

from app.core.exceptions import ModelNotLoadedError
from app.ml import inference
from app.ml.model_loader import ModelLoader


def test_predict_sales_selecciona_solo_las_columnas_del_modelo(fake_model_loader):
    X = pd.DataFrame({"f1": [1.0], "f2": [2.0], "columna_extra_no_usada": [99.0]})
    result = inference.predict_sales(fake_model_loader, X)
    assert result.iloc[0] == 42.0


def test_predict_churn_devuelve_probabilidad(fake_model_loader):
    X = pd.DataFrame({"a": [1], "b": [2]})
    result = inference.predict_churn(fake_model_loader, X)
    assert "churn_probability" in result.columns
    assert result["churn_probability"].iloc[0] == 0.3


def test_detect_anomalies_devuelve_prediccion_y_score(fake_model_loader):
    X = pd.DataFrame({"a": [1]})
    result = inference.detect_anomalies(fake_model_loader, X)
    assert result["is_anomaly_pred"].iloc[0] == 1
    assert result["anomaly_score"].iloc[0] == 0.2


def test_get_recommendations_filtra_por_item_history(fake_model_loader):
    result = inference.get_recommendations(fake_model_loader, item_history=["A1"])
    assert len(result) == 1
    assert result.iloc[0]["item_A"] == "A1"


def test_get_recommendations_sin_historial_devuelve_top(fake_model_loader):
    result = inference.get_recommendations(fake_model_loader, item_history=None)
    assert len(result) == 2


def test_predict_goal_growth_ratio_es_float(fake_model_loader):
    X = pd.DataFrame({"anio": [2026], "mes": [7]})
    result = inference.predict_goal_growth_ratio(fake_model_loader, X)
    assert isinstance(result, float)
    assert result == 42.0


def test_model_loader_get_lanza_domain_error_si_no_esta_cargado():
    loader = ModelLoader(models_dir="/nonexistent")
    with pytest.raises(ModelNotLoadedError):
        loader.get("sales_rf")


def test_model_loader_is_ready_falso_sin_modelos():
    loader = ModelLoader(models_dir="/nonexistent")
    assert loader.is_ready() is False
