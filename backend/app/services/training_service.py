# backend/app/services/training_service.py
"""Orquesta el reentrenamiento de modelos ML como subprocess externo (scripts de
`ml/src/training/`, fuera de `backend/`). Rename de `mlops_service.py`: el estado que
antes era un dict global a nivel de módulo (`_mlops_status`, no gestionado por ningún
ciclo de vida) ahora es un atributo de instancia, y la instancia vive en
`app.state.training_service` (mismo patrón Singleton-vía-lifespan que `ModelLoader`).

Corrige un bug preexistente: el cálculo del `project_root` via `../../..` desde este
archivo asumía que WORKDIR de Docker era la raíz del repo, pero con
`WORKDIR /app` + `COPY . .` del build context `./backend`, esa aritmética resolvía a
`/` (raíz del filesystem del contenedor), no a `/app` -- el reentrenamiento ya estaba
roto en Docker antes de este refactor. Ahora usa `settings.ML_SOURCE_DIR` explícito."""
import logging
import os
import subprocess
import sys
from datetime import datetime
from typing import Any

from app.core.config import settings
from app.core.exceptions import ExternalDataError

logger = logging.getLogger("Backend.TrainingService")

TRAINING_SCRIPTS = [
    os.path.join("src", "data", "make_dataset.py"),
    os.path.join("src", "training", "train_sales_prediction.py"),
    os.path.join("src", "training", "train_demand_forecasting.py"),
    os.path.join("src", "training", "train_churn_prediction.py"),
    os.path.join("src", "training", "train_recommendation_engine.py"),
    os.path.join("src", "training", "train_customer_segmentation.py"),
    os.path.join("src", "training", "train_anomaly_detection.py"),
]


class TrainingService:
    def __init__(self, ml_source_dir: str | None = None):
        self.ml_source_dir = ml_source_dir or settings.ML_SOURCE_DIR
        self._status: dict[str, Any] = {
            "is_training": False,
            "last_run": None,
            "last_status": "Idle",  # Idle, Running, Success, Failed
            "logs": [],
        }

    def get_status(self) -> dict[str, Any]:
        return self._status

    def _log(self, msg: str) -> None:
        logger.info(msg)
        self._status["logs"].append(f"{datetime.now().isoformat()} - {msg}")
        if len(self._status["logs"]) > 50:
            self._status["logs"].pop(0)

    def trigger_retraining_pipeline(self) -> None:
        """Ejecuta los scripts de entrenamiento en secuencia. Pensado para correr en
        background (`BackgroundTasks`)."""
        if self._status["is_training"]:
            logger.warning("Intento de iniciar entrenamiento mientras ya hay uno en curso.")
            return

        if not os.path.isdir(self.ml_source_dir):
            # En "prod-like" (sin el mount de código fuente de ml/) este endpoint debe
            # fallar con un mensaje claro en vez de colgarse o fallar oscuro -- antes el
            # bug de path (ver docstring del módulo) producía justamente eso.
            self._status["last_status"] = "Failed"
            self._status["last_run"] = datetime.now().isoformat()
            raise ExternalDataError(
                f"Reentrenamiento no disponible: el código fuente de ml/ no está montado "
                f"en este entorno ({self.ml_source_dir}). El reentrenamiento en producción "
                f"debe ejecutarse vía el servicio 'ml' del docker-compose (perfil ml)."
            )

        self._status.update(is_training=True, last_status="Running", logs=[])
        self._log(f"Iniciando pipeline de MLOps desde {self.ml_source_dir}")

        python_exec = sys.executable
        try:
            for script_rel in TRAINING_SCRIPTS:
                script = os.path.join(self.ml_source_dir, script_rel)
                if not os.path.exists(script):
                    self._log(f"Omitiendo {script_rel} por no encontrar el archivo.")
                    continue

                self._log(f"Ejecutando: {script_rel}")
                result = subprocess.run(
                    [python_exec, script],
                    capture_output=True, text=True, cwd=self.ml_source_dir,
                )
                if result.returncode != 0:
                    self._log(f"FALLO en {script_rel}: {result.stderr[:200]}")
                    raise ExternalDataError(f"Pipeline interrumpido por fallo en {script_rel}")
                self._log(f"Éxito: {script_rel}")

            self._log("Todos los modelos entrenados y generados en ml_models exitosamente.")
            self._status["last_status"] = "Success"
        except Exception as e:
            logger.error(f"Error en el pipeline de MLOps: {e}")
            self._status["last_status"] = "Failed"
            raise
        finally:
            self._status["is_training"] = False
            self._status["last_run"] = datetime.now().isoformat()
