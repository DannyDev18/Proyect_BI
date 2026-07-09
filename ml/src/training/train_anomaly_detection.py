# ml/src/training/train_anomaly_detection.py
import logging
from sklearn.ensemble import IsolationForest
from src.utils.model_export import save_artifact

logger = logging.getLogger("ML.AnomalyDetection")

def train_isolation_forest(X_train, contamination=0.01):
    """
    Entrena un Isolation Forest para detectar anomalías (Unsupervised).
    Esperado usar sobre transacciones (df_facturas) con features como 
    descuentos_extremos, horas_anormales_cancelacion, montos_atípicos.
    El contamintation asume que el 1% histórico o menos fue fraude/error.
    """
    logger.info(f"Entrenando motor de Detección de Anomalías (Isolation Forest, cont={contamination})...")
    
    # IsolationForest no stricta homogeneizar la escala como K-Means, pero 
    # si se usa StandardScaler previamente mejora la simetría espacial de árboles.
    model = IsolationForest(
        n_estimators=200, 
        max_samples='auto', 
        contamination=contamination,
        random_state=42
    )
    
    # En entrenamiento no supervisado, el modelo marca inliers(1) vs outliers(-1)
    model.fit(X_train)
    logger.info("Modelo de Anomalías entrenado exitosamente.")
    
    return model

def save_anomaly_model(model, filepath=None, metrics=None):
    save_artifact(
        model, "isolation_forest_model.pkl", filepath=filepath, metrics=metrics,
        extra={"problema": "deteccion_anomalias_no_supervisada"},
    )
