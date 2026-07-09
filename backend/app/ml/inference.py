# backend/app/ml/inference.py
"""Funciones puras de inferencia: reciben un `ModelLoader` + DataFrame, sin acceso a
DB/HTTP. Esto es lo que se testea con un `ModelLoader` fake (modelo dummy) sin
necesitar los `.pkl` reales -- ver backend/tests/unit/test_inference.py."""
import pandas as pd

from app.ml.model_loader import ModelLoader


def predict_sales(loader: ModelLoader, X: pd.DataFrame) -> pd.Series:
    model = loader.get('sales_rf')
    X = X[model.feature_names_in_]
    return pd.Series(model.predict(X))


def predict_demand(loader: ModelLoader, X: pd.DataFrame) -> pd.Series:
    model = loader.get('demand_rf')
    X = X[model.feature_names_in_]
    return pd.Series(model.predict(X))


def predict_churn(loader: ModelLoader, X: pd.DataFrame) -> pd.DataFrame:
    model = loader.get('churn_rf')
    preds = model.predict(X)
    probs = model.predict_proba(X)[:, 1]  # probabilidad de clase 1 (churn)
    return pd.DataFrame({'is_churn_pred': preds, 'churn_probability': probs})


def detect_anomalies(loader: ModelLoader, X: pd.DataFrame) -> pd.Series:
    model = loader.get('anomaly')
    # 1 = normal, -1 = anomalía (convención de IsolationForest)
    return pd.Series(model.predict(X))


def get_recommendations(loader: ModelLoader, item_history: list | None = None) -> pd.DataFrame:
    rules = loader.get('association')
    if item_history:
        return rules[rules['item_A'].isin(item_history)].head(5)
    return rules.head(10)


def predict_segmentation(loader: ModelLoader, X_rfm: pd.DataFrame) -> pd.Series:
    model = loader.get('segmentation')
    return pd.Series(model.predict(X_rfm))


def predict_goal_growth_ratio(loader: ModelLoader, X: pd.DataFrame) -> float:
    """Unifica el caso que antes cargaba `goals_rf_model.pkl` con un `joblib.load()`
    inline dentro de `GoalsAutomationService` -- ahora usa el mismo `ModelLoader` que
    los otros 6 modelos (clave 'goals_rf')."""
    model = loader.get('goals_rf')
    return float(model.predict(X)[0])
