# backend/app/ml/model_loader.py
"""Carga y cachea en memoria los modelos ML (.pkl) entrenados por el pipeline de `ml/`.

Reemplaza dos mecanismos previos e inconsistentes:
1. La variable global `predictor` de `prediction_service.py` (side-effect de import,
   con manipulación manual de `sys.path` para importar `ml.src.prediction.predict_model`).
2. El `joblib.load()` inline de `goals_rf_model.pkl` dentro de `GoalsAutomationService`.

Se instancia UNA vez en el `lifespan` de `main.py` y vive en `app.state.model_loader`
(Singleton gestionado por el ciclo de vida de FastAPI, no por import). El único punto de
extensión para agregar un modelo nuevo es el diccionario `_MODEL_FILES`: no se justifica
un Factory Pattern formal porque los 6 modelos son 100% joblib/sklearn-compatible
(incluyendo XGBoost/CatBoost/LightGBM vía wrapper sklearn) -- no hay una segunda familia
de carga (ONNX, etc.) hoy que amerite esa indirection.

Fase 4 (docs/ml_contracts.md, docs/auditoria/12_fase0_analisis_capa_contratos_ml.md):
apunta a los artefactos reconstruidos bajo contrato (`ml/contracts/models/*.json`) y lee
el sidecar `<modelo>.meta.json` (montado junto al .pkl en el mismo volumen de solo
lectura) para obtener el orden de columnas de entrenamiento, en vez de depender de
`model.feature_names_in_` -- atributo que no todos los estimadores exponen (p.ej.
CatBoost envuelto en TransformedTargetRegressor, H-07) y que un Pipeline (segmentación)
tampoco expone de forma uniforme.
"""
import json
import os
import logging
from typing import Any

import joblib

from app.core.exceptions import ModelNotLoadedError
from app.ml.contract_validation import ModelContractLite, load_contract

logger = logging.getLogger("Backend.ModelLoader")

# clave usada por services/ml -> nombre de archivo .pkl reconstruido bajo contrato
# (ml/contracts/models/*.json); coincide con `contract_name` en el sidecar .meta.json.
_MODEL_FILES: dict[str, str] = {
    'sales_rf': 'sales.pkl',
    'demand_rf': 'demand.pkl',
    'churn_rf': 'churn.pkl',
    'segmentation': 'segmentation.pkl',
    'association': 'recommendation.pkl',
    'anomaly': 'anomalies.pkl',
}


class ModelLoader:
    """Cachea en memoria los modelos `.pkl` disponibles en `models_dir` junto con el
    contenido de su sidecar `.meta.json` (features, métricas, cluster_to_segment, etc.)."""

    def __init__(self, models_dir: str, contracts_dir: str | None = None):
        self.models_dir = models_dir
        self.contracts_dir = contracts_dir
        self._models: dict[str, Any] = {}
        self._meta: dict[str, dict[str, Any]] = {}
        self._contracts: dict[str, ModelContractLite] = {}

    def load_all(self) -> None:
        """Carga todos los modelos declarados en `_MODEL_FILES`. Tolera archivos
        faltantes (logea WARNING) -- útil en dev sin todos los .pkl disponibles;
        cada llamada a `get()` fallará explícitamente para el modelo faltante."""
        for key, filename in _MODEL_FILES.items():
            path = os.path.join(self.models_dir, filename)
            if not os.path.exists(path):
                logger.warning(f"Modelo '{filename}' no encontrado en {path}. No se carga.")
                continue
            try:
                self._models[key] = joblib.load(path)
                self._meta[key] = self._load_meta_sidecar(path)
                if self.contracts_dir:
                    contract_name = os.path.splitext(filename)[0]  # 'sales.pkl' -> 'sales'
                    contract = load_contract(self.contracts_dir, contract_name)
                    if contract:
                        self._contracts[key] = contract
                logger.info(f"Modelo '{key}' cargado desde {filename} (features: {len(self.get_features(key))}).")
            except Exception as e:
                logger.error(f"Fallo al cargar '{filename}': {e}")

    @staticmethod
    def _load_meta_sidecar(pkl_path: str) -> dict[str, Any]:
        meta_path = os.path.splitext(pkl_path)[0] + ".meta.json"
        if not os.path.exists(meta_path):
            return {}
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"No se pudo leer el sidecar {meta_path}: {e}")
            return {}

    def get(self, key: str) -> Any:
        """Devuelve el modelo cacheado o lanza ModelNotLoadedError (antes: ValueError
        genérico repetido en cada método de MultiModelPredictor)."""
        model = self._models.get(key)
        if model is None:
            raise ModelNotLoadedError(f"El modelo '{key}' no está cargado.")
        return model

    def is_loaded(self, key: str) -> bool:
        return key in self._models

    def is_ready(self) -> bool:
        """Al menos un modelo cargado -- usado por el healthcheck extendido."""
        return len(self._models) > 0

    def keys(self) -> list[str]:
        """Claves internas declaradas en `_MODEL_FILES` (M-02: panel MLOps de
        Administrador itera esto para reportar el estado de cada modelo, cargado o no)."""
        return list(_MODEL_FILES.keys())

    def get_meta(self, key: str) -> dict[str, Any]:
        """Sidecar `.meta.json` completo del modelo (features, metrics, cluster_to_segment,
        target_transform, etc.). Diccionario vacío si el modelo no cargó o no tiene sidecar
        (artefacto legacy)."""
        return self._meta.get(key, {})

    def get_features(self, key: str) -> list[str]:
        """Orden de columnas de entrenamiento declarado en el contrato (fuente de verdad
        del sidecar, no `model.feature_names_in_`)."""
        return self.get_meta(key).get('features', [])

    def get_contract(self, key: str) -> ModelContractLite | None:
        """Contrato declarativo (`ml/contracts/models/<name>.json`) del modelo, si el
        volumen `ML_CONTRACTS_DIR` está montado y el JSON existe. `None` en caso
        contrario -- `app/ml/contract_validation.py` degrada con gracia (no bloquea)."""
        return self._contracts.get(key)

    def verify_library_versions(self) -> None:
        """M-01 (docs/features/plan_mejoras_proyecto.md): compara `library_versions` del
        sidecar `.meta.json` de cada modelo cargado contra la librería realmente instalada
        en este proceso. sklearn no garantiza compatibilidad de pickles entre versiones
        (`InconsistentVersionWarning`) -- eso puede producir predicciones silenciosamente
        distintas, no solo un crash, así que el warning de sklearn (que nadie mira en los
        logs) se promueve aquí a un ERROR explícito y agregado por librería."""
        import catboost
        import lightgbm
        import sklearn
        import xgboost

        installed = {
            "scikit-learn": sklearn.__version__,
            "xgboost": xgboost.__version__,
            "lightgbm": lightgbm.__version__,
            "catboost": catboost.__version__,
        }

        for key, meta in self._meta.items():
            trained_versions = meta.get("library_versions", {})
            for lib, trained_version in trained_versions.items():
                current_version = installed.get(lib)
                if current_version and current_version != trained_version:
                    logger.error(
                        f"Drift de versión de librería ML para el modelo '{key}': "
                        f"'{lib}' fue serializado con {trained_version} pero el proceso "
                        f"actual tiene {current_version}. Las predicciones pueden diferir "
                        f"silenciosamente del modelo entrenado (ver M-01, plan_mejoras_proyecto.md)."
                    )

    def get_training_date(self, key: str) -> str:
        """Fecha de modificación del archivo .pkl (proxy de 'fecha de entrenamiento').
        Corrige un bug previo: el código viejo buscaba el nombre de archivo hardcodeado
        `sales_rf_model.pkl` (obsoleto) en vez del nombre real cargado (`sales_best_model.pkl`),
        por lo que siempre caía al valor por defecto "Reciente"."""
        filename = _MODEL_FILES.get(key)
        if not filename:
            return "Desconocida"
        path = os.path.join(self.models_dir, filename)
        if not os.path.exists(path):
            return "Reciente"
        import datetime
        return datetime.datetime.fromtimestamp(os.path.getmtime(path)).strftime('%Y-%m-%d')
