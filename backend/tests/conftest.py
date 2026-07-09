# backend/tests/conftest.py
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("PG_HOST", "localhost")
os.environ.setdefault("PG_PORT", "5433")
os.environ.setdefault("ENV", "development")


@pytest.fixture
def fake_db_session():
    """`Session` de SQLAlchemy simulada -- para repositorios/servicios que no deben
    tocar Postgres en tests unitarios."""
    return MagicMock()


@pytest.fixture
def fake_model_loader():
    """`ModelLoader` con un modelo dummy en vez de los .pkl reales -- usado por los
    tests de `app/ml/inference.py` y de servicios que dependen de él."""
    from app.ml.model_loader import ModelLoader

    loader = ModelLoader(models_dir="/nonexistent")
    loader._models = {
        "sales_rf": _DummyRegressor(feature_names=["f1", "f2"]),
        "demand_rf": _DummyRegressor(feature_names=["f1", "f2"]),
        "churn_rf": _DummyClassifier(),
        "anomaly": _DummyAnomalyDetector(),
        "segmentation": _DummyClusterer(),
        "association": _dummy_rules_df(),
        "goals_rf": _DummyRegressor(feature_names=["anio", "mes"]),
    }
    return loader


class _DummyRegressor:
    def __init__(self, feature_names):
        import numpy as np
        self.feature_names_in_ = np.array(feature_names)

    def predict(self, X):
        import numpy as np
        return np.array([42.0] * len(X))


class _DummyClassifier:
    def predict(self, X):
        import numpy as np
        return np.array([0] * len(X))

    def predict_proba(self, X):
        import numpy as np
        return np.array([[0.7, 0.3]] * len(X))


class _DummyAnomalyDetector:
    def predict(self, X):
        import numpy as np
        return np.array([1] * len(X))  # 1 = normal


class _DummyClusterer:
    def predict(self, X):
        import numpy as np
        return np.array([2] * len(X))


def _dummy_rules_df():
    import pandas as pd
    return pd.DataFrame({
        "item_A": ["A1", "A2"],
        "item_B": ["B1", "B2"],
        "score": [0.8, 0.6],
    })
