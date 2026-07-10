import logging

import numpy as np
import pandas as pd
from sklearn.metrics import r2_score
from sklearn.model_selection import train_test_split

from src.training.model_selector import find_best_regression_model
from src.utils.model_export import library_versions, save_artifact

logger = logging.getLogger("ML.GoalsTrainer")


def train_goals_prediction(df_raw: pd.DataFrame):
    logger.info("=== 7. ENTRENANDO PREDICCIÓN DE METAS (VENTAS) COMPITIENDO === ")

    if df_raw.empty or len(df_raw) < 10:
        logger.error("Datos insuficientes para entrenamiento de Metas.")
        return None, {}, []

    # Sort chronologically to prevent Time Series Data Leakage
    df_raw = df_raw.sort_values(by=['anio', 'mes'])

    # 'estacionalidad_mes_objetivo' se excluye a propósito: en backtest, su versión cruda es
    # colineal con 'indice_estacional_relativo' (que ya la normaliza contra el nivel actual)
    # y degrada el R2 al combinarse (0.06 vs 0.17 solo con el índice). Ver
    # ml/REPORTE_MEJORA_MODELOS.md.
    # 'anio' se excluye también (H-13a, docs/auditoria/11_auditoria_tecnica_modelos_ml.md):
    # como feature numérica cruda, los árboles no extrapolan a años futuros nunca vistos en
    # entrenamiento (2027 se trataría, en el mejor caso, como "igual que el año más reciente
    # visto"). La señal de tendencia interanual ya la aportan ventas_anio_anterior y
    # promedio_movil_3m; 'mes' sí se conserva porque su rango (1-12) es cerrado y se repite.
    features = [col for col in df_raw.columns if col not in [
        'y_ventas_futuras', 'id_vendedor_origen', 'sucursal', 'vendedor_sk', 'sucursal_sk',
        'estacionalidad_mes_objetivo', 'anio',
    ]]
    X = df_raw[features].fillna(0)
    y = df_raw['y_ventas_futuras'].fillna(1.0)

    # Simple split sin shuffle para preservar orden temporal (80% Train, 20% Test futuro)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)

    logger.info(f"Entrenando Competencia RFR, XGB, LGBM con {len(X_train)} muestras... Features: {features}")
    best_model = find_best_regression_model(X_train, y_train, is_log_transformed=False, cv_splits=3)

    # H-13b: antes un `except: pass` silenciaba cualquier fallo de evaluación; ahora se
    # loguea explícitamente y las métricas se devuelven para persistirlas en el sidecar.
    metrics = {}
    try:
        preds = best_model.predict(X_test)
        metrics = {
            "R2": float(r2_score(y_test, preds)),
            "MAE": float(np.mean(np.abs(y_test - preds))),
        }
        logger.info(f"R2 Score del modelo de Growth Ratio de Metas en Validación Test Split Múltiple: {metrics['R2']:.4f}")
    except Exception as exc:
        logger.warning(f"No se pudo evaluar el modelo de metas en el holdout: {exc}")

    return best_model, metrics, features


def save_goals_model(model, filepath=None, metrics=None, features=None, data_range=None):
    """H-13c: migrado de `joblib.dump` directo a `save_artifact` (pkl + sidecar
    `.meta.json`) -- antes era el único de los 7 modelos sin metadata."""
    if model is None:
        return
    save_artifact(
        model, "goals.pkl", filepath=filepath,
        algorithm=type(model).__name__,
        features=features,
        metrics=metrics or {},
        contract_name="goals",
        contract_version="0.1.0",
        library_versions_used=library_versions("scikit-learn", "xgboost", "lightgbm", "catboost"),
        data_range=data_range,
        extra={"problema": "regresion_ratio_crecimiento", "target": "y_ventas_futuras (ratio, capped 1.5)"},
    )
    logger.info("Modelo de Metas competitivo guardado (con sidecar de metadatos).")
