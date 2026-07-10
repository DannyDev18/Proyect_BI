import logging
import numpy as np
from sklearn.base import clone
from sklearn.compose import TransformedTargetRegressor
from src.training.model_selector import find_best_regression_model, evaluate_reg
from src.utils.model_export import save_artifact, library_versions

logger = logging.getLogger("ML.Trainer")

def evaluate_model(y_true, y_pred, is_log_transformed=False):
    """`is_log_transformed=False` por defecto: desde H-01 el modelo devuelve USD
    directamente (TransformedTargetRegressor autocontenido), no log1p."""
    return evaluate_reg(y_true, y_pred, is_log_transformed)

def train_sales_model(X_train, y_train, hyperparameter_search=True):
    """
    Compite XGBoost, LightGBM, CatBoost, RF y HGB (vía model_selector) sobre el target en
    escala log1p (altísima asimetría, kurtosis 2800), y envuelve al ganador en un
    TransformedTargetRegressor(func=log1p, inverse_func=expm1) antes de devolverlo.

    H-01 (docs/auditoria/11_auditoria_tecnica_modelos_ml.md): el .pkl anterior predecía en
    espacio log1p y el serving lo consumía crudo (venta diaria de ~12 en vez de ~160.000
    USD). El artefacto resultante de esta función es autocontenido: predict(X) devuelve
    USD directamente, sin que ninguna capa de serving deba 'recordar' aplicar expm1.
    """
    y_train_log = np.log1p(y_train)
    logger.info("Iniciando competencia automática de Varios Algoritmos para Predicción de Ventas Principales...")

    best_model = find_best_regression_model(X_train, y_train_log, is_log_transformed=True, cv_splits=3)

    wrapped_model = TransformedTargetRegressor(
        regressor=clone(best_model),
        func=np.log1p,
        inverse_func=np.expm1,
    )
    wrapped_model.fit(X_train, y_train)
    return wrapped_model

def save_model(model, filepath=None, metrics=None, features=None, data_range=None):
    save_artifact(
        model, "sales.pkl", filepath=filepath, metrics=metrics,
        algorithm=type(model.regressor_).__name__,
        features=features,
        contract_name="sales",
        contract_version="0.1.0",
        library_versions_used=library_versions("scikit-learn", "xgboost", "lightgbm", "catboost"),
        data_range=data_range,
        target_transform="log1p",
        extra={"problema": "regresion_serie_temporal", "target": "y_sales_net (USD, artefacto autocontenido)"},
    )
