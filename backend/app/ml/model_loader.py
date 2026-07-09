# backend/app/ml/model_loader.py
"""Carga y cachea en memoria los modelos ML (.pkl) entrenados por el pipeline de `ml/`.

Reemplaza dos mecanismos previos e inconsistentes:
1. La variable global `predictor` de `prediction_service.py` (side-effect de import,
   con manipulación manual de `sys.path` para importar `ml.src.prediction.predict_model`).
2. El `joblib.load()` inline de `goals_rf_model.pkl` dentro de `GoalsAutomationService`.

Se instancia UNA vez en el `lifespan` de `main.py` y vive en `app.state.model_loader`
(Singleton gestionado por el ciclo de vida de FastAPI, no por import). El único punto de
extensión para agregar un modelo nuevo es el diccionario `_MODEL_FILES`: no se justifica
un Factory Pattern formal porque los 7 modelos son 100% joblib/sklearn-compatible
(incluyendo XGBoost/CatBoost/LightGBM vía wrapper sklearn) -- no hay una segunda familia
de carga (ONNX, etc.) hoy que amerite esa indirection.
"""
import os
import logging
from typing import Any

import joblib

from app.core.exceptions import ModelNotLoadedError

logger = logging.getLogger("Backend.ModelLoader")

# clave usada por services/ml -> nombre de archivo .pkl (el GANADOR de la competencia
# multi-algoritmo entrenada en ml/src/training/, no un RandomForest base).
_MODEL_FILES: dict[str, str] = {
    'sales_rf': 'sales_best_model.pkl',
    'demand_rf': 'demand_best_model.pkl',
    'churn_rf': 'churn_best_classifier.pkl',
    'segmentation': 'kmeans_rfm_model.pkl',
    'association': 'association_rules.pkl',
    'anomaly': 'isolation_forest_model.pkl',
    'goals_rf': 'goals_best_model.pkl',
}


class ModelLoader:
    """Cachea en memoria los modelos `.pkl` disponibles en `models_dir`."""

    def __init__(self, models_dir: str):
        self.models_dir = models_dir
        self._models: dict[str, Any] = {}

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
                logger.info(f"Modelo '{key}' cargado desde {filename}.")
            except Exception as e:
                logger.error(f"Fallo al cargar '{filename}': {e}")

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
