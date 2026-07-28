# ml/src/training/train_customer_segmentation.py
import logging

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import davies_bouldin_score, silhouette_score
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


def evaluar_estabilidad_k(df_rfm, k_range=range(2, 9)) -> list[dict]:
    """Método del codo + silueta + Davies-Bouldin para K=2..8 (Fase 4, docs/features/
    plan_mejora_pipeline_ml.md §6: "documentar estabilidad de K", no supervisado por lo
    que no hay split 80/20 -- este barrido es el sustituto metodológico: justifica que
    K=4 no es arbitrario, comparándolo contra vecinos). Se corre ANTES del entrenamiento
    final para que quede en el sidecar como evidencia, sin afectar el K elegido (K=4 es
    una decisión de negocio -- 4 segmentos accionables para Ventas, no solo estadística).
    """
    resultados = []
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(df_rfm)
    for k in k_range:
        km = KMeans(n_clusters=k, init="k-means++", random_state=42, n_init=10)
        labels = km.fit_predict(X_scaled)
        fila = {"k": k, "inertia": float(km.inertia_)}
        try:
            fila["silhouette"] = float(silhouette_score(X_scaled, labels))
            fila["davies_bouldin"] = float(davies_bouldin_score(X_scaled, labels))
        except ValueError:
            fila["silhouette"] = None
            fila["davies_bouldin"] = None
        resultados.append(fila)
        logger.info(
            f"  > K={k}: inertia={fila['inertia']:.1f}, silhouette={fila['silhouette']}, "
            f"davies_bouldin={fila['davies_bouldin']}"
        )
    return resultados


def train_rfm_segmentation(df_rfm, n_clusters=4) -> tuple[Pipeline, float | None, float | None]:
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
    davies_bouldin = None
    try:
        X_scaled = pipeline.named_steps["scaler"].transform(df_rfm)
        score = float(silhouette_score(X_scaled, cluster_labels))
        davies_bouldin = float(davies_bouldin_score(X_scaled, cluster_labels))
        logger.info(f"Score de Silueta del cluster (Unsupervised Metric): {score:.4f}")
        logger.info(f"Davies-Bouldin (menor=mejor separación entre clusters): {davies_bouldin:.4f}")
    except ValueError:
        logger.warning("Data insuficiente para calcular el coeficiente de silueta/Davies-Bouldin.")

    return pipeline, score, davies_bouldin


def save_segmentation_model(
    pipeline: Pipeline, filepath=None, silhouette: float | None = None, n_rows: int | None = None,
    davies_bouldin: float | None = None, estabilidad_k: list[dict] | None = None,
):
    scaler = pipeline.named_steps["scaler"]
    kmeans = pipeline.named_steps["kmeans"]
    order = _order_clusters_by_value(kmeans, scaler)
    cluster_to_segment = {int(cluster_id): SEGMENT_NAMES_BY_VALUE[rank] for rank, cluster_id in enumerate(order)}

    # Perfil de negocio de cada clúster (Fase 4 §6: "perfil de negocio de cada clúster"),
    # en la escala RFM real (no escalada) -- centroides invertidos, mismo cálculo que
    # _order_clusters_by_value.
    centroids_reales = scaler.inverse_transform(kmeans.cluster_centers_)
    perfil_clusters = {
        cluster_to_segment[int(cid)]: {
            "recency_promedio": round(float(centroids_reales[cid, 0]), 2),
            "frequency_promedio": round(float(centroids_reales[cid, 1]), 2),
            "monetary_value_promedio": round(float(centroids_reales[cid, 2]), 2),
        }
        for cid in range(len(centroids_reales))
    }

    metrics = {}
    if silhouette is not None:
        metrics["silhouette"] = silhouette
    if davies_bouldin is not None:
        metrics["davies_bouldin"] = davies_bouldin

    save_artifact(
        pipeline, "segmentation.pkl", filepath=filepath,
        algorithm="Pipeline(StandardScaler+KMeans)",
        features=["recency", "frequency", "monetary_value"],
        registry_key="segmentation",
        metrics=metrics,
        contract_name="segmentation",
        contract_version="0.1.0",
        library_versions_used=library_versions("scikit-learn"),
        extra={
            "cluster_to_segment": cluster_to_segment,
            "n_rows_entrenamiento": n_rows,
            "perfil_clusters": perfil_clusters,
            "estabilidad_k": estabilidad_k,
        },
    )
    logger.info(f"Pipeline de Segmentación guardado. Mapeo cluster->segmento: {cluster_to_segment}")
