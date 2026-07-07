# backend/app/api/v1/endpoints/admin_mlops.py
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from app.core.deps import PermissionChecker
from app.models.user import User
from app.services import mlops_service
from pydantic import BaseModel
from typing import Dict, Any, List

router = APIRouter()

admin_checker = PermissionChecker(allowed_roles=["administrador"])

class MLOpsStatusResponse(BaseModel):
    is_training: bool
    last_run: str | None
    last_status: str
    logs: List[str]

@router.post("/retrain")
def trigger_model_retraining(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(admin_checker)
):
    """
    Desencadena el proceso completo de MLOps: 
    Extracción de datos (Feature Store) y reentrenamiento de los modelos (.pkl).
    El proceso se ejecuta en un hilo de background y actualiza su estado en memoria.
    Solo administradores tienen acceso.
    """
    status = mlops_service.get_mlops_status()
    if status["is_training"]:
        raise HTTPException(
            status_code=409, 
            detail="Un proceso de entrenamiento ya está en curso."
        )
        
    background_tasks.add_task(mlops_service.trigger_retraining_pipeline)
    
    return {"message": "Pipeline de reentrenamiento iniciado en background."}

@router.get("/status", response_model=MLOpsStatusResponse)
def get_mlops_status(
    current_user: User = Depends(admin_checker)
) -> MLOpsStatusResponse:
    """
    Devuelve el estado actual de los pipelines de ML, 
    incluyendo logs y resultado de la última corrida.
    """
    status = mlops_service.get_mlops_status()
    return MLOpsStatusResponse(
        is_training=status["is_training"],
        last_run=status["last_run"],
        last_status=status["last_status"],
        logs=status["logs"]
    )
