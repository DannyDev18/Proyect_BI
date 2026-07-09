# backend/app/api/routes/admin_ml.py
"""Rename de `admin_mlops.py`. Dispara y consulta el estado del reentrenamiento de
modelos (orquestado por `TrainingService`, subprocess externo de `ml/src/training/`)."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.api.dependencies import TrainingServiceDep
from app.core.deps import PermissionChecker
from app.schemas.mlops import MLOpsStatusResponse

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

    background_tasks.add_task(training_service.trigger_retraining_pipeline)
    return {"message": "Pipeline de reentrenamiento iniciado en background."}


@router.get("/status", response_model=MLOpsStatusResponse, dependencies=[Depends(admin_checker)])
def get_mlops_status(training_service: TrainingServiceDep) -> MLOpsStatusResponse:
    """Estado actual del pipeline de reentrenamiento, incluyendo logs y última corrida."""
    status = training_service.get_status()
    return MLOpsStatusResponse(**status)
