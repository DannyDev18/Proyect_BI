import logging
import numpy as np
from src.training.model_selector import find_best_regression_model, evaluate_reg
from src.utils.model_export import save_artifact

logger = logging.getLogger("ML.DemandForecasting")

def evaluate_demand_model(y_true, y_pred, is_log_transformed=True):
    return evaluate_reg(y_true, y_pred, is_log_transformed)

def train_demand_forecaster(X_train, y_train, hyperparameter_search=True):
    """
    Entrena automatizadamente múltiples algoritmos competitivos para demanda.
    """
    y_train_log = np.log1p(y_train)
    logger.info("Iniciando competencia automática para Proyección de Demanda Logística...")
    best_model = find_best_regression_model(X_train, y_train_log, is_log_transformed=True, cv_splits=3)
    return best_model

def save_demand_model(model, filepath=None, metrics=None):
    save_artifact(
        model, "demand_best_model.pkl", filepath=filepath, metrics=metrics,
        extra={"problema": "regresion_serie_temporal", "target": "y_quantity (log1p)"},
    )
