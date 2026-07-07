# ml/src/training/train_customer_segmentation.py
import logging
import os
import joblib
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score

logger = logging.getLogger("ML.CustomerSegmentation")

def train_rfm_segmentation(df_rfm, n_clusters=4):
    """
    Recibe un DataFrame con métricas RFM (Recency, Frequency, Monetary) precalculadas 
    por cliente desde el EDW y entrena un K-Means para segmentación comercial.
    """
    logger.info(f"Entrenando motor K-Means para Segmentación RFM (Clusters={n_clusters})...")
    
    # K-Means es fuertemente reactivo a las escalas (dinero vs días), siempre usar StandardScaler
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(df_rfm)
    
    model = KMeans(n_clusters=n_clusters, init='k-means++', random_state=42, n_init=10)
    cluster_labels = model.fit_predict(X_scaled)
    
    # Evaluación no supervisada
    try:
        score = silhouette_score(X_scaled, cluster_labels)
        logger.info(f"Score de Silueta del cluster (Unsupervised Metric): {score:.4f}")
    except ValueError:
        logger.warning("Data insuficiente para predecir coeficientes de silueta.")
        
    return {'model': model, 'scaler': scaler}

def save_segmentation_model(artifacts, filepath=None):
    if filepath is None:
        filepath = os.path.join(os.getenv("ML_MODELS_DIR", "./models"), "kmeans_rfm_model.pkl")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    joblib.dump(artifacts, filepath)
    logger.info(f"Pipeline de Segmentación guardado en: {filepath}")
