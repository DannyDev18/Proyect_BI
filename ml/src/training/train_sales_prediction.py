import logging
import numpy as np
from sklearn.base import clone
from sklearn.compose import TransformedTargetRegressor
from sklearn.ensemble import RandomForestRegressor
from src.training.model_selector import find_best_regression_model, evaluate_reg
from src.utils.model_export import save_artifact, library_versions

logger = logging.getLogger("ML.Trainer")

# Modelo final fijado con evidencia en docs/auditoria/22_plan_mejora_modelo_ventas.md
# (Fases 1-3, protocolo de 3 corridas por configuración): RandomForest con parámetros por
# defecto y 500 árboles supera en el holdout cronológico (R2=0.2985±0.0040, MAE=3780,
# RMSE=6279) tanto a los 5 algoritmos con búsqueda profunda de hiperparámetros
# (RandomizedSearchCV n_iter=25; mejor: RF tuneado R2=0.258) como a la regresión por
# cuantiles y a SARIMAX. La búsqueda por CV elige configuraciones que rinden PEOR en el
# holdout que estos defaults, así que la competencia queda solo como modo opcional
# (hyperparameter_search=True) para re-evaluaciones futuras.
GANADOR_SALES_PARAMS = {"n_estimators": 500, "random_state": 42, "n_jobs": -1}

def evaluate_model(y_true, y_pred, is_log_transformed=False):
    """`is_log_transformed=False` por defecto: desde H-01 el modelo devuelve USD
    directamente (TransformedTargetRegressor autocontenido), no log1p."""
    return evaluate_reg(y_true, y_pred, is_log_transformed)

def train_sales_model(X_train, y_train, hyperparameter_search=False):
    """
    Entrena el modelo FINAL de ventas (contrato sales v0.3.0): RandomForestRegressor con
    GANADOR_SALES_PARAMS (ver evidencia arriba), envuelto en un
    TransformedTargetRegressor(func=log1p, inverse_func=expm1) por la altísima asimetría
    del target (kurtosis 2800).

    `hyperparameter_search=True` re-corre la competencia de algoritmos del model_selector
    (RF/XGB/LGBM/CatBoost/HGB con RandomizedSearchCV) en vez del ganador fijo -- solo para
    re-evaluaciones metodológicas; en este dataset rinde peor que el ganador fijo (ver
    docs/auditoria/22_plan_mejora_modelo_ventas.md §5).

    H-01 (docs/auditoria/11_auditoria_tecnica_modelos_ml.md): el .pkl anterior predecía en
    espacio log1p y el serving lo consumía crudo (venta diaria de ~12 en vez de ~160.000
    USD). El artefacto resultante de esta función es autocontenido: predict(X) devuelve
    USD directamente, sin que ninguna capa de serving deba 'recordar' aplicar expm1.
    """
    if hyperparameter_search:
        logger.info("Iniciando competencia automática de algoritmos (modo re-evaluación)...")
        y_train_log = np.log1p(y_train)
        best_model = find_best_regression_model(X_train, y_train_log, is_log_transformed=True, cv_splits=3)
        regressor = clone(best_model)
    else:
        logger.info("Entrenando modelo final fijado con evidencia (RF 500 árboles, doc 22)...")
        regressor = RandomForestRegressor(**GANADOR_SALES_PARAMS)

    wrapped_model = TransformedTargetRegressor(
        regressor=regressor,
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
        contract_version="0.3.0",
        library_versions_used=library_versions("scikit-learn", "xgboost", "lightgbm", "catboost"),
        data_range=data_range,
        target_transform="log1p",
        extra={"problema": "regresion_serie_temporal", "target": "y_sales_net (USD, artefacto autocontenido)"},
    )
