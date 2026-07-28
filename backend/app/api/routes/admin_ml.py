# backend/app/api/routes/admin_ml.py
"""Rename de `admin_mlops.py`. Dispara y consulta el estado del reentrenamiento de
modelos (Fase 3, docs/features/plan_mejora_pipeline_ml.md §5: orquestado por
`TrainingService` vía `docker compose run ml` con gating de campeón único), y expone
el historial de corridas (`public.ml_model_runs`) y las versiones archivadas
disponibles para promoción manual/rollback."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.api.dependencies import ModelLoaderDep, MLModelRunRepositoryDep, TrainingServiceDep
from app.core.deps import PermissionChecker
from app.core.exceptions import ExternalDataError
from app.ml.model_loader import MODEL_DISPLAY_NAMES
from app.schemas.mlops import (
    MLOpsStatusResponse, ModelRunResponse, ModelStatusResponse, ModelVersionResponse,
    PromoteRequest, RetrainRequest,
)
from app.schemas.pagination import Page, PaginationParams, pagination_params, paginar

router = APIRouter()

admin_checker = PermissionChecker(allowed_roles=["administrador"])


@router.post("/retrain", dependencies=[Depends(admin_checker)])
def trigger_model_retraining(
    body: RetrainRequest, background_tasks: BackgroundTasks, training_service: TrainingServiceDep,
):
    """Desencadena el reentrenamiento (con gating) de un modelo (`body.clave`) o de los 6
    (`clave="all"`, default) en background, vía `docker compose run --rm ml ...`. Solo
    administradores tienen acceso."""
    status = training_service.get_status()
    if status["is_training"]:
        raise HTTPException(status_code=409, detail="Un proceso de entrenamiento ya está en curso.")

    # Validación síncrona antes de encolar (docs/auditoria/36_actualizacion_modulo_admin.md,
    # H9): el cliente debe recibir el error de inmediato, no enterrado en
    # `GET /admin/modelos/status` tras un 200 falso.
    try:
        training_service.verificar_disponible()
    except ExternalDataError as e:
        raise HTTPException(status_code=400, detail=str(e))

    background_tasks.add_task(training_service.trigger_retraining_pipeline, body.clave, "panel_admin")
    return {"message": f"Reentrenamiento de '{body.clave}' iniciado en background."}


@router.post("/promote", dependencies=[Depends(admin_checker)])
def promote_model_version(body: PromoteRequest, training_service: TrainingServiceDep):
    """Promoción manual: fuerza como campeón una versión archivada (p.ej. una que el
    gating automático había rechazado, si un humano decide que sí vale la pena)."""
    try:
        return training_service.promote_model(body.clave, body.version, disparado_por="panel_admin_promote")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ExternalDataError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/rollback", dependencies=[Depends(admin_checker)])
def rollback_model_version(body: PromoteRequest, training_service: TrainingServiceDep):
    """Rollback: mismo mecanismo que `/promote` (apuntar `registry.json` a una versión
    archivada existente), con `disparado_por` distinto para diferenciarlo en el
    historial de `GET /runs`. No requiere reentrenar."""
    try:
        return training_service.promote_model(body.clave, body.version, disparado_por="panel_admin_rollback")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ExternalDataError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/runs", response_model=Page[ModelRunResponse], dependencies=[Depends(admin_checker)])
def get_model_runs(
    run_repo: MLModelRunRepositoryDep,
    clave: str | None = None,
    pagination: PaginationParams = Depends(pagination_params),
) -> Page[ModelRunResponse]:
    """Historial paginado de corridas de gating (promovidas y rechazadas) desde
    `public.ml_model_runs`."""
    runs = run_repo.get_recientes(clave=clave)
    return paginar([ModelRunResponse.model_validate(r) for r in runs], pagination)


@router.get("/{clave}/versions", response_model=list[ModelVersionResponse], dependencies=[Depends(admin_checker)])
def get_model_versions(clave: str, model_loader: ModelLoaderDep) -> list[ModelVersionResponse]:
    """Versiones archivadas de un modelo (`ml/models/versions/<clave>/`), para elegir a
    cuál hacer rollback o promoción manual desde el panel."""
    return [ModelVersionResponse(**v) for v in model_loader.get_versions(clave)]


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
