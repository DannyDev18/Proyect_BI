# ml/src/training/train_anomaly_detection.py
import logging
import numpy as np
from sklearn.ensemble import IsolationForest
from src.utils.model_export import library_versions, save_artifact

logger = logging.getLogger("ML.AnomalyDetection")

# Fase 4 (docs/features/plan_mejora_pipeline_ml.md §6): antes `contamination=0.01` era un
# valor fijo sin justificación empírica. Se acota el criterio data-driven (ver
# `estimar_contamination_iqr`) a este rango: menos de 0.5% se considera ruido de la
# propia varianza del negocio, más de 5% ya no es "anomalía" sino un régimen normal
# distinto (mismo principio de acotar techo/piso de sanidad que usa
# `IQRGoalCalculationEngine` en el backend para metas).
CONTAMINATION_MIN = 0.005
CONTAMINATION_MAX = 0.05


def estimar_contamination_iqr(df_txs, columna: str = "margen") -> float:
    """Estima la proporción esperada de anomalías a partir de la regla IQR clásica
    (Q1 - 1.5*IQR, Q3 + 1.5*IQR) sobre `columna` -- mismo criterio de detección de
    outliers que ya usa `IQRGoalCalculationEngine` para metas comerciales, en vez de
    asumir a priori que "el 1% histórico fue fraude/error" sin evidencia. El resultado
    se acota a [CONTAMINATION_MIN, CONTAMINATION_MAX] porque IsolationForest exige
    `contamination` en (0, 0.5] y un valor fuera de ese rango angosto ya no es un ajuste
    razonable de sensibilidad."""
    serie = df_txs[columna].dropna()
    q1, q3 = serie.quantile(0.25), serie.quantile(0.75)
    iqr = q3 - q1
    piso, techo = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    tasa_outliers = float(((serie < piso) | (serie > techo)).mean())
    contamination = float(np.clip(tasa_outliers, CONTAMINATION_MIN, CONTAMINATION_MAX))
    logger.info(
        f"  > Tasa de outliers IQR en '{columna}': {tasa_outliers:.4%} -> "
        f"contamination={contamination:.4f} (acotado a [{CONTAMINATION_MIN}, {CONTAMINATION_MAX}])"
    )
    return contamination


def train_isolation_forest(X_train, contamination=0.01):
    """
    Entrena un Isolation Forest para detectar anomalías (Unsupervised).
    Esperado usar sobre transacciones (df_facturas) con features como
    descuentos_extremos, horas_anormales_cancelacion, montos_atípicos.
    `contamination` se estima con `estimar_contamination_iqr` antes de llamar a esta
    función (Fase 4) -- el default 0.01 solo aplica si el caller no lo calcula.
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

def save_anomaly_model(model, filepath=None, metrics=None, features=None, data_range=None, extra_meta=None):
    extra = {"problema": "deteccion_anomalias_no_supervisada"}
    if extra_meta:
        extra.update(extra_meta)
    save_artifact(
        model, "anomalies.pkl", filepath=filepath, metrics=metrics,
        algorithm=type(model).__name__,
        features=features,
        registry_key="anomaly",
        contract_name="anomalies",
        contract_version="0.1.0",
        library_versions_used=library_versions("scikit-learn"),
        data_range=data_range,
        population_filter="costo_total IS NOT NULL; estado_documento_sk <> -1",
        extra=extra,
    )
