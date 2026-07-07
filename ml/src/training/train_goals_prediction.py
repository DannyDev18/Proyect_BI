import logging
import os
import joblib
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from src.training.model_selector import find_best_regression_model

logger = logging.getLogger("ML.GoalsTrainer")

def train_goals_prediction(df_raw: pd.DataFrame):
    logger.info("=== 7. ENTRENANDO PREDICCIÓN DE METAS (VENTAS) COMPITIENDO === ")
    
    if df_raw.empty or len(df_raw) < 10:
        logger.error("Datos insuficientes para entrenamiento de Metas.")
        return None
        
    # Sort chronologically to prevent Time Series Data Leakage
    df_raw = df_raw.sort_values(by=['anio', 'mes'])
    
    features = [col for col in df_raw.columns if col not in ['y_ventas_futuras', 'id_vendedor_origen', 'sucursal', 'vendedor_sk', 'sucursal_sk']]
    X = df_raw[features].fillna(0)
    y = df_raw['y_ventas_futuras'].fillna(1.0)
    
    # Simple split sin shuffle para preservar orden temporal (80% Train, 20% Test futuro)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)
    
    logger.info(f"Entrenando Competencia RFR, XGB, LGBM con {len(X_train)} muestras... Features: {features}")
    best_model = find_best_regression_model(X_train, y_train, is_log_transformed=False, cv_splits=3)
    
    try:
        preds = best_model.predict(X_test)
        from sklearn.metrics import r2_score
        score = r2_score(y_test, preds)
        logger.info(f"R2 Score del modelo de Growth Ratio de Metas en Validación Test Split Múltiple: {score:.4f}")
    except Exception as e:
         pass
         
    return best_model

def save_goals_model(model, filepath=None):
    if model is None:
        return
    if filepath is None:
        filepath = os.path.join(os.getenv("ML_MODELS_DIR", "./models"), "goals_best_model.pkl")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    joblib.dump(model, filepath)
    logger.info(f"Modelo de Metas competitivo guardado en: {filepath}")
