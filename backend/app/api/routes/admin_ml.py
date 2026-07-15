# backend/app/api/routes/admin_ml.py
"""Rename de `admin_mlops.py`. Dispara y consulta el estado del reentrenamiento de
modelos (orquestado por `TrainingService`, subprocess externo de `ml/src/training/`)."""
import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.api.dependencies import ModelLoaderDep, TrainingServiceDep
from app.core.deps import PermissionChecker
from app.ml.model_loader import MODEL_DISPLAY_NAMES
from app.schemas.mlops import MLOpsStatusResponse, ModelStatusResponse

router = APIRouter()

admin_checker = PermissionChecker(allowed_roles=["administrador"])


@router.post("/retrain", dependencies=[Depends(admin_checker)])
def trigger_model_retraining(background_tasks: BackgroundTasks, training_service: TrainingServiceDep):
    """
    Desencadena el pipeline completo de MLOps (extracción de datos + reentrenamiento de
    los `.pkl`) en background. Solo administradores tienen acceso.
    """
    status = training_service.get_status()
    if status["is_training"]:
        raise HTTPException(status_code=409, detail="Un proceso de entrenamiento ya está en curso.")

    # Validación síncrona antes de encolar (docs/auditoria/36_actualizacion_modulo_admin.md,
    # H9): antes esta verificación solo ocurría dentro del propio background task, así que
    # el cliente ya recibía un 200 "iniciado" falso en entornos sin `ml/` montado (prod-like)
    # y el fallo real quedaba enterrado en `GET /admin/modelos/status`, que nadie consulta
    # proactivamente.
    if not os.path.isdir(training_service.ml_source_dir):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Reentrenamiento no disponible: el código fuente de ml/ no está montado en "
                f"este entorno ({training_service.ml_source_dir}). El reentrenamiento en "
                f"producción debe ejecutarse vía el servicio 'ml' del docker-compose (perfil ml)."
            ),
        )

    background_tasks.add_task(training_service.trigger_retraining_pipeline)
    return {"message": "Pipeline de reentrenamiento iniciado en background."}


@router.get("/status", response_model=MLOpsStatusResponse, dependencies=[Depends(admin_checker)])
def get_mlops_status(training_service: TrainingServiceDep) -> MLOpsStatusResponse:
    """Estado actual del pipeline de reentrenamiento, incluyendo logs y última corrida."""
    status = training_service.get_status()
    return MLOpsStatusResponse(**status)


@router.get("/models", response_model=list[ModelStatusResponse], dependencies=[Depends(admin_checker)])
def get_models_status(model_loader: ModelLoaderDep) -> list[ModelStatusResponse]:
    """Estado de carga y métrica principal (R²) de cada uno de los 6 modelos ML servidos
    desde `ml/models/*.meta.json` (M-02: reemplaza el mock `MODEL_STATUS`)."""
    resultado = []
    for key in model_loader.keys():
        cargado = model_loader.is_loaded(key)
        metricas = model_loader.get_meta(key).get("metrics", {}) if cargado else {}
        resultado.append(ModelStatusResponse(
            name=MODEL_DISPLAY_NAMES.get(key, key),
            r2=metricas.get("R2"),
            status="OK" if cargado else "NO_CARGADO",
        ))
    return resultado
