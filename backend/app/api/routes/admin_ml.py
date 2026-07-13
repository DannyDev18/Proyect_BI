# backend/app/api/routes/admin_ml.py
"""Rename de `admin_mlops.py`. Dispara y consulta el estado del reentrenamiento de
modelos (orquestado por `TrainingService`, subprocess externo de `ml/src/training/`)."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.api.dependencies import ModelLoaderDep, TrainingServiceDep
from app.core.deps import PermissionChecker
from app.schemas.mlops import MLOpsStatusResponse, ModelStatusResponse

router = APIRouter()

admin_checker = PermissionChecker(allowed_roles=["administrador"])

# Nombre de negocio por modelo (M-02: panel MLOps del DashboardAdmin, reemplaza el mock
# MODEL_STATUS). Claves = _MODEL_FILES de app/ml/model_loader.py.
_NOMBRE_MODELO = {
    "sales_rf": "Random Forest (Ventas)",
    "demand_rf": "Random Forest (Demanda)",
    "churn_rf": "Clasificador de Churn",
    "segmentation": "K-Means RFM (Segmentación)",
    "association": "Apriori (Venta Cruzada)",
    "anomaly": "Isolation Forest (Anomalías)",
}


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


@router.get("/models", response_model=list[ModelStatusResponse], dependencies=[Depends(admin_checker)])
def get_models_status(model_loader: ModelLoaderDep) -> list[ModelStatusResponse]:
    """Estado de carga y métrica principal (R²) de cada uno de los 6 modelos ML servidos
    desde `ml/models/*.meta.json` (M-02: reemplaza el mock `MODEL_STATUS`)."""
    resultado = []
    for key in model_loader.keys():
        cargado = model_loader.is_loaded(key)
        metricas = model_loader.get_meta(key).get("metrics", {}) if cargado else {}
        resultado.append(ModelStatusResponse(
            name=_NOMBRE_MODELO.get(key, key),
            r2=metricas.get("R2"),
            status="OK" if cargado else "NO_CARGADO",
        ))
    return resultado
