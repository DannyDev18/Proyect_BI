import logging
from sklearn.metrics import accuracy_score, classification_report, roc_auc_score
from src.training.model_selector import find_best_classification_model
from src.utils.model_export import library_versions, save_artifact

logger = logging.getLogger("ML.ChurnPrediction")

def evaluate_churn_classifier(y_true, y_pred, y_proba):
    """Devuelve las métricas como dict (antes solo se logueaban, H-18: el sidecar quedaba
    con metrics: {})."""
    logger.info("\n--- Classification Report (CHURN) ---")
    logger.info("\n" + classification_report(y_true, y_pred))
    metrics = {"accuracy": accuracy_score(y_true, y_pred)}
    if y_proba is not None:
        try:
            metrics["roc_auc"] = roc_auc_score(y_true, y_proba[:, 1])
            logger.info(f"ROC AUC Score: {metrics['roc_auc']:.4f}")
        except ValueError as exc:
            logger.warning(f"No se pudo calcular ROC AUC: {exc}")
    return metrics

def train_churn_model(X_train, y_train):
    logger.info("Entrenando Clasificador competitivo Multi-Boosting para Predicción de Abandono...")
    best_model = find_best_classification_model(X_train, y_train, cv_splits=3)
    return best_model

def save_churn_model(model, filepath=None, metrics=None, features=None, data_range=None):
    save_artifact(
        model, "churn.pkl", filepath=filepath, metrics=metrics,
        algorithm=type(model).__name__,
        features=features,
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
