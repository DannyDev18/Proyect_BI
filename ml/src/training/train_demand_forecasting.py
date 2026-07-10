import logging
import numpy as np
from sklearn.base import clone
from sklearn.compose import TransformedTargetRegressor
from src.training.model_selector import find_best_regression_model, evaluate_reg
from src.utils.model_export import save_artifact, library_versions

logger = logging.getLogger("ML.DemandForecasting")

def evaluate_demand_model(y_true, y_pred, is_log_transformed=False):
    """`is_log_transformed=False` por defecto: desde H-01 el modelo devuelve unidades
    directamente (TransformedTargetRegressor autocontenido), no log1p."""
    return evaluate_reg(y_true, y_pred, is_log_transformed)

def train_demand_forecaster(X_train, y_train, hyperparameter_search=True):
    """
    Compite múltiples algoritmos sobre el target en escala log1p y envuelve al ganador en
    un TransformedTargetRegressor(func=log1p, inverse_func=expm1) autocontenido (H-01,
    mismo patrón que train_sales_prediction.py).
    """
    y_train_log = np.log1p(y_train)
    logger.info("Iniciando competencia automática para Proyección de Demanda Logística...")
    best_model = find_best_regression_model(X_train, y_train_log, is_log_transformed=True, cv_splits=3)

    wrapped_model = TransformedTargetRegressor(
        regressor=clone(best_model),
        func=np.log1p,
        inverse_func=np.expm1,
    )
    wrapped_model.fit(X_train, y_train)
    return wrapped_model

def save_demand_model(model, filepath=None, metrics=None, features=None, data_range=None):
    save_artifact(
        model, "demand.pkl", filepath=filepath, metrics=metrics,
        algorithm=type(model.regressor_).__name__,
        features=features,
        contract_name="demand",
        contract_version="0.1.0",
        library_versions_used=library_versions("scikit-learn", "xgboost", "lightgbm", "catboost"),
        data_range=data_range,
        target_transform="log1p",
        extra={"problema": "regresion_serie_temporal", "target": "y_quantity (unidades, artefacto autocontenido)"},
    )
