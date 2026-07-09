import logging
from sklearn.metrics import classification_report, roc_auc_score
from src.training.model_selector import find_best_classification_model
from src.utils.model_export import save_artifact

logger = logging.getLogger("ML.ChurnPrediction")

def evaluate_churn_classifier(y_true, y_pred, y_proba):
    logger.info("\n--- Classification Report (CHURN) ---")
    logger.info("\n" + classification_report(y_true, y_pred))
    if y_proba is not None:
        try:
            auc = roc_auc_score(y_true, y_proba[:, 1])
            logger.info(f"ROC AUC Score: {auc:.4f}")
        except:
             pass

def train_churn_model(X_train, y_train):
    logger.info("Entrenando Clasificador competitivo Multi-Boosting para Predicción de Abandono...")
    best_model = find_best_classification_model(X_train, y_train, cv_splits=3)
    return best_model

def save_churn_model(model, filepath=None, metrics=None):
    save_artifact(
        model, "churn_best_classifier.pkl", filepath=filepath, metrics=metrics,
        extra={"problema": "clasificacion_binaria", "target": "is_churn (recency > umbral)"},
    )
