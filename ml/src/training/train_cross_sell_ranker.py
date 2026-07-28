# ml/src/training/train_cross_sell_ranker.py
"""Entrenamiento del 7º modelo del proyecto: `cross_sell_ranker` (Fase 2, docs/features/
plan_refactor_venta_cruzada_ia.md). Reutiliza `find_best_classification_model`
(competencia RF/XGBoost/LightGBM/CatBoost, igual que churn) -- lo específico de este
modelo es el DATASET (ml/src/features/cross_sell_ranker_features.py) y el BACKTEST
contra la línea base del item-item (ml/src/training/backtest_recommendation.py), no el
algoritmo de entrenamiento en sí."""
import logging

from sklearn.metrics import (
    accuracy_score, average_precision_score, confusion_matrix, f1_score,
    precision_score, recall_score, roc_auc_score,
)

from src.training.model_selector import find_best_classification_model
from src.utils.model_export import library_versions, save_artifact

logger = logging.getLogger("ML.CrossSellRanker")


def train_ranker(X_train, y_train):
    logger.info("Entrenando ranker de Venta Cruzada (competencia RF/XGBoost/LightGBM/CatBoost)...")
    return find_best_classification_model(X_train, y_train, cv_splits=3)


def evaluate_ranker(y_true, y_pred, y_proba) -> dict:
    matriz = confusion_matrix(y_true, y_pred)
    tn, fp, fn, tp = matriz.ravel()
    metrics = {
        "accuracy": accuracy_score(y_true, y_pred),
        "precision": precision_score(y_true, y_pred, zero_division=0),
        "recall": recall_score(y_true, y_pred, zero_division=0),
        "f1": f1_score(y_true, y_pred, zero_division=0),
        "confusion_matrix_tn": int(tn), "confusion_matrix_fp": int(fp),
        "confusion_matrix_fn": int(fn), "confusion_matrix_tp": int(tp),
    }
    if y_proba is not None:
        proba_positiva = y_proba[:, 1]
        metrics["roc_auc"] = roc_auc_score(y_true, proba_positiva)
        metrics["pr_auc"] = average_precision_score(y_true, proba_positiva)
    return metrics


def save_cross_sell_ranker_model(model, filepath=None, metrics=None, features=None, data_range=None, extra_meta=None):
    return save_artifact(
        model, "cross_sell_ranker.pkl", filepath=filepath, metrics=metrics,
        algorithm=type(model).__name__,
        features=features,
        registry_key="cross_sell_ranker",
        contract_name="cross_sell_ranker",
        contract_version="0.1.0",
        library_versions_used=library_versions("scikit-learn", "xgboost", "lightgbm", "catboost"),
        data_range=data_range,
        population_filter="cliente_sk <> -1; producto_sk <> -1; estado_documento_sk <> -1; NOT es_devolucion",
        extra={
            "problema": "clasificacion_binaria_ranking",
            "target": "label (¿compró el candidato en (T, T+ML_RANKER_HORIZONTE_DIAS]? -- corte temporal, mismo patrón anti-fuga que churn H-05)",
            **(extra_meta or {}),
        },
    )
