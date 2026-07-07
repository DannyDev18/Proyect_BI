import logging
import os
import joblib
import numpy as np
from src.training.model_selector import find_best_regression_model, evaluate_reg

logger = logging.getLogger("ML.Trainer")

def evaluate_model(y_true, y_pred, is_log_transformed=True):
    return evaluate_reg(y_true, y_pred, is_log_transformed)

def train_sales_model(X_train, y_train, hyperparameter_search=True):
    """
    Entrena compitiendo XGBoost, LightGBM, CatBoost, RF y HGB a través de model_selector.
    """
    # Usaremos Transformación Logarítmica del Target dada su altísima asimetría (Kurtosis 2800)
    y_train_log = np.log1p(y_train)
    logger.info("Iniciando competencia automática de Varios Algoritmos para Predicción de Ventas Principales...")
    
    best_model = find_best_regression_model(X_train, y_train_log, is_log_transformed=True, cv_splits=3)
    return best_model

def save_model(model, filepath=None):
    if filepath is None:
        filepath = os.path.join(os.getenv("ML_MODELS_DIR", "./models"), "sales_best_model.pkl")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    joblib.dump(model, filepath)
    logger.info(f"Modelo Guardado exitosamente en: {filepath}")
