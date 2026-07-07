# backend/app/services/mlops_service.py
import sys
import os
import subprocess
import logging
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger("Backend.MLOpsService")

# Estado en memoria global
_mlops_status = {
    "is_training": False,
    "last_run": None,
    "last_status": "Idle",  # Idle, Success, Failed
    "logs": []
}

def get_mlops_status() -> Dict[str, Any]:
    """Retorna el estado actual del proceso de reentrenamiento de modelos."""
    return _mlops_status

def log_status(msg: str):
    logger.info(msg)
    _mlops_status["logs"].append(f"{datetime.now().isoformat()} - {msg}")
    # Mantener sólo los últimos 50 logs
    if len(_mlops_status["logs"]) > 50:
        _mlops_status["logs"].pop(0)

def trigger_retraining_pipeline():
    """
    Orquesta el pipeline completo de machine learning en background.
    Asume que el root del proyecto es C:\Proyect_BI o `/app` en docker.
    """
    if _mlops_status["is_training"]:
        logger.warning("Intento de iniciar entrenamiento mientras ya hay uno en curso.")
        return

    _mlops_status["is_training"] = True
    _mlops_status["last_status"] = "Running"
    _mlops_status["logs"] = []
    
    # Resolver path base
    curr_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(curr_dir, "..", "..", ".."))
    
    ml_dir = os.path.join(project_root, "ml")
    python_exec = sys.executable

    log_status(f"Iniciando pipeline de MLOps en {project_root}")
    
    scripts = [
        # 1. Extracción de datos
        os.path.join(ml_dir, "src", "data", "make_dataset.py"),
        # 2. Entrenamiento de modelos
        os.path.join(ml_dir, "src", "training", "train_sales_prediction.py"),
        os.path.join(ml_dir, "src", "training", "train_demand_forecasting.py"),
        os.path.join(ml_dir, "src", "training", "train_churn_prediction.py"),
        os.path.join(ml_dir, "src", "training", "train_recommendation_engine.py"),
        os.path.join(ml_dir, "src", "training", "train_customer_segmentation.py"),
        os.path.join(ml_dir, "src", "training", "train_anomaly_detection.py")
    ]

    try:
        for script in scripts:
            if not os.path.exists(script):
                log_status(f"Omitiendo {script} por no encontrar el archivo.")
                continue
                
            log_status(f"Ejecutando: {os.path.basename(script)}")
            result = subprocess.run(
                [python_exec, script],
                capture_output=True,
                text=True,
                cwd=project_root # Correr desde root para resolver paths internos del .py
            )
            
            if result.returncode != 0:
                log_status(f"FALLO en {os.path.basename(script)}")
                log_status(f"Error: {result.stderr[:200]}")
                raise Exception(f"Pipeline interrumpido por fallo en {os.path.basename(script)}")
            else:
                log_status(f"Éxito: {os.path.basename(script)}")

        # Notificar a la app que recargue los modelos (Opcional, requiere reinicio o reloading state)
        log_status("Todos los modelos entrenados y generados en /ml_models exitosamente.")
        _mlops_status["last_status"] = "Success"
        _mlops_status["last_run"] = datetime.now().isoformat()
        
    except Exception as e:
        logger.error(f"Error en MLOps pipeline: {e}")
        _mlops_status["last_status"] = "Failed"
        _mlops_status["last_run"] = datetime.now().isoformat()
    finally:
        _mlops_status["is_training"] = False
