# ml/src/training/train_customer_segmentation.py
import logging

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.utils.model_export import library_versions, save_artifact

logger = logging.getLogger("ML.CustomerSegmentation")

# Nombres de negocio ordenados por valor esperado del segmento, de mayor a menor. Tras
# ordenar los clusters por sus centroides (ver _order_clusters_by_value), el cluster con
# mayor valor (monetary alto, recency baja) recibe el primer nombre, y así el mapeo
# cluster_id -> nombre de negocio queda estable entre reentrenamientos (H-12) en vez de
# depender de la etiqueta arbitraria que K-Means asigna cada corrida.
SEGMENT_NAMES_BY_VALUE = ["Campeones", "Leales", "En Riesgo", "Perdidos"]


def _order_clusters_by_value(kmeans: KMeans, scaler: StandardScaler) -> list[int]:
    """cluster_id ordenados de MAYOR a MENOR valor (monetary alto, recency baja).

    Los centroides viven en el espacio escalado; se invierte el escalado para comparar
    magnitudes RFM reales. Asume columnas [recency, frequency, monetary_value] en ese
    orden -- contrato del dataset RFM (ml/contracts/models/segmentation.json)."""
    centroids = scaler.inverse_transform(kmeans.cluster_centers_)
    recency, monetary = centroids[:, 0], centroids[:, 2]
    value_score = monetary - recency
    return list(np.argsort(-value_score))


def train_rfm_segmentation(df_rfm, n_clusters=4) -> tuple[Pipeline, float | None]:
    """Entrena un Pipeline sklearn autocontenido (StandardScaler + KMeans) sobre RFM
    (recency, frequency, monetary_value).

    Antes se serializaba como dict {'model', 'scaler'} y el backend rompía al llamar
    .predict() sobre el dict (H-02, docs/auditoria/11_auditoria_tecnica_modelos_ml.md).
    Con un Pipeline único, predict(X) escala y clasifica en una sola llamada -- ningún
    caller necesita "recordar" invocar scaler.transform() por separado.
    """
    logger.info(f"Entrenando pipeline K-Means para Segmentación RFM (Clusters={n_clusters})...")

    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("kmeans", KMeans(n_clusters=n_clusters, init="k-means++", random_state=42, n_init=10)),
    ])
    cluster_labels = pipeline.fit_predict(df_rfm)

    score = None
    try:
        score = float(silhouette_score(pipeline.named_steps["scaler"].transform(df_rfm), cluster_labels))
        logger.info(f"Score de Silueta del cluster (Unsupervised Metric): {score:.4f}")
    except ValueError:
        logger.warning("Data insuficiente para calcular el coeficiente de silueta.")

    return pipeline, score


def save_segmentation_model(pipeline: Pipeline, filepath=None, silhouette: float | None = None, n_rows: int | None = None):
    scaler = pipeline.named_steps["scaler"]
    kmeans = pipeline.named_steps["kmeans"]
    order = _order_clusters_by_value(kmeans, scaler)
    cluster_to_segment = {int(cluster_id): SEGMENT_NAMES_BY_VALUE[rank] for rank, cluster_id in enumerate(order)}

    save_artifact(
        pipeline, "segmentation.pkl", filepath=filepath,
        algorithm="Pipeline(StandardScaler+KMeans)",
        features=["recency", "frequency", "monetary_value"],
        metrics={"silhouette": silhouette} if silhouette is not None else {},
        contract_name="segmentation",
        contract_version="0.1.0",
        library_versions_used=library_versions("scikit-learn"),
        extra={
            "cluster_to_segment": cluster_to_segment,
            "n_rows_entrenamiento": n_rows,
        },
    )
    logger.info(f"Pipeline de Segmentación guardado. Mapeo cluster->segmento: {cluster_to_segment}")
