import logging
import catboost as cb
import numpy as np
from sklearn.metrics import (
    accuracy_score, average_precision_score, classification_report, confusion_matrix,
    f1_score, precision_recall_curve, precision_score, recall_score, roc_auc_score,
)
from sklearn.model_selection import RandomizedSearchCV, StratifiedKFold
from src.utils.model_export import library_versions, save_artifact

logger = logging.getLogger("ML.ChurnPrediction")

def evaluate_churn_classifier(y_true, y_pred, y_proba):
    """Devuelve las métricas como dict (antes solo se logueaban, H-18: el sidecar quedaba
    con metrics: {}).

    Fase 4 (docs/features/plan_mejora_pipeline_ml.md §6, D-7, petición explícita del
    usuario): antes solo se guardaban accuracy+roc_auc. Se agregan matriz de confusión,
    precision/recall/F1 (umbral por defecto 0.5, el que usa `model.predict()`), PR-AUC
    (más informativa que ROC-AUC bajo desbalance de clases) y una calibración de umbral
    -- el umbral que maximiza F1 sobre este mismo holdout, reportado solo como
    DIAGNÓSTICO para la model card. El serving real NO usa este umbral: el backend
    filtra `churn_probability` contra `settings.CHURN_UMBRAL_RIESGO_ALTO`, un umbral de
    NEGOCIO ("¿a quién priorizo en la lista de trabajo?"), no el óptimo estadístico de
    F1 -- ambos criterios responden preguntas distintas y no deben confundirse."""
    logger.info("\n--- Classification Report (CHURN, umbral=0.5) ---")
    logger.info("\n" + classification_report(y_true, y_pred))

    matriz = confusion_matrix(y_true, y_pred)
    tn, fp, fn, tp = matriz.ravel()
    metrics = {
        "accuracy": accuracy_score(y_true, y_pred),
        "precision": precision_score(y_true, y_pred, zero_division=0),
        "recall": recall_score(y_true, y_pred, zero_division=0),
        "f1": f1_score(y_true, y_pred, zero_division=0),
        "confusion_matrix_tn": int(tn),
        "confusion_matrix_fp": int(fp),
        "confusion_matrix_fn": int(fn),
        "confusion_matrix_tp": int(tp),
    }
    if y_proba is not None:
        try:
            proba_positiva = y_proba[:, 1]
            metrics["roc_auc"] = roc_auc_score(y_true, proba_positiva)
            metrics["pr_auc"] = average_precision_score(y_true, proba_positiva)
            logger.info(f"ROC AUC Score: {metrics['roc_auc']:.4f} | PR-AUC: {metrics['pr_auc']:.4f}")

            precisions, recalls, umbrales = precision_recall_curve(y_true, proba_positiva)
            f1_por_umbral = np.divide(
                2 * precisions * recalls, precisions + recalls,
                out=np.zeros_like(precisions), where=(precisions + recalls) > 0,
            )
            idx_mejor = int(np.argmax(f1_por_umbral[:-1])) if len(umbrales) else None
            if idx_mejor is not None:
                metrics["umbral_optimo_f1"] = float(umbrales[idx_mejor])
                metrics["f1_en_umbral_optimo"] = float(f1_por_umbral[idx_mejor])
                logger.info(
                    f"Calibración de umbral (solo diagnóstico): F1 óptimo={metrics['f1_en_umbral_optimo']:.4f} "
                    f"en umbral={metrics['umbral_optimo_f1']:.4f} (serving usa CHURN_UMBRAL_RIESGO_ALTO, no este valor)."
                )
        except ValueError as exc:
            logger.warning(f"No se pudo calcular métricas de probabilidad: {exc}")
    logger.info(f"Matriz de confusión [[TN={tn}, FP={fp}], [FN={fn}, TP={tp}]]")
    return metrics

def train_churn_model(X_train, y_train):
    """Un solo algoritmo fijo (CatBoost), no una competencia multi-modelo -- decisión
    explícita del usuario (2026-08-04): antes se corría `find_best_classification_model`
    (RF/XGBoost/LightGBM/CatBoost compitiendo por ROC-AUC en cada reentrenamiento), pero
    CatBoost ya es el campeón consistente en `ml/models/churn.meta.json`
    (`ml/REPORTE_MEJORA_MODELOS.md`); mantener las otras 3 familias solo agregaba tiempo
    de entrenamiento sin cambiar el resultado. `find_best_classification_model` (
    `model_selector.py`) se conserva intacta para `train_cross_sell_ranker.py`, que sí
    sigue en competencia (contrato en `draft`, nunca promovido -- no tiene un campeón
    fijo que justifique lo mismo)."""
    logger.info("Entrenando CatBoostClassifier (único algoritmo, ver docstring) para Predicción de Abandono...")
    cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
    search = RandomizedSearchCV(
        estimator=cb.CatBoostClassifier(random_state=42, verbose=0, auto_class_weights='Balanced'),
        param_distributions={
            'iterations': [100, 200],
            'learning_rate': [0.01, 0.1],
            'depth': [4, 6],
        },
        n_iter=4,
        cv=cv,
        scoring='roc_auc',
        random_state=42,
        n_jobs=1,  # CatBoost ya paraleliza internamente (ver model_selector.py).
    )
    search.fit(X_train, y_train)
    logger.info(f"CatBoost mejor ROC-AUC de validación: {search.best_score_:.4f} | params: {search.best_params_}")
    return search.best_estimator_

def save_churn_model(model, filepath=None, metrics=None, features=None, data_range=None):
    save_artifact(
        model, "churn.pkl", filepath=filepath, metrics=metrics,
        algorithm=type(model).__name__,
        features=features,
        registry_key="churn_rf",
        contract_name="churn",
        contract_version="0.1.0",
        library_versions_used=library_versions("scikit-learn", "xgboost", "lightgbm", "catboost"),
        data_range=data_range,
        population_filter="cliente_sk <> -1; estado_documento_sk <> -1",
        extra={
            "problema": "clasificacion_binaria",
            "target": "is_churn (¿NO vuelve a comprar en (T, T+90]? -- corte temporal, H-05)",
        },
    )
