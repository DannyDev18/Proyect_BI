# backend/app/api/dependencies.py
"""Dependencias FastAPI compartidas entre routers: fábricas de repositorios/servicios
(Dependency Injection) y la dependencia `resolve_sucursal_filter` que antes estaba
duplicada copy-pasted en 6+ endpoints de `analytics.py`."""
from typing import Annotated

from fastapi import Depends, Request

from app.core.deps import CurrentUserDep, SessionDep
from app.ml.model_loader import ModelLoader
from app.repositories.analytics_repository import AnalyticsRepository
from app.repositories.audit_repository import AuditRepository
from app.repositories.cartera360_repository import Cartera360Repository
from app.repositories.catalog_repository import CatalogRepository
from app.repositories.commission_config_repository import CommissionConfigRepository
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.goal_repository import GoalRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.prediction_repository import PredictionRepository
from app.repositories.recommendation_event_repository import RecommendationEventRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.system_repository import SystemRepository
from app.repositories.user_repository import UserRepository
from app.repositories.warehouse_repository import WarehouseRepository
from app.services.analytics_service import AnalyticsService
from app.services.audit_service import AuditService
from app.services.cartera360_service import Cartera360Service
from app.services.commission_config_service import CommissionConfigService
from app.services.commission_service import CommissionService
from app.services.commission_simulation_service import CommissionSimulationService
from app.services.goal_ml_service import GoalMLService
from app.services.goals_service import GoalsService
from app.services.notification_service import NotificationService
from app.services.prediction_service import PredictionService
from app.services.role_service import RoleService
from app.services.system_service import SystemService
from app.services.training_service import TrainingService
from app.services.user_service import UserService
from app.services.warehouse_service import WarehouseService


# ── Repositorios ─────────────────────────────────────────────────────────────
def get_user_repository(db: SessionDep) -> UserRepository:
    return UserRepository(db)


def get_role_repository(db: SessionDep) -> RoleRepository:
    return RoleRepository(db)


def get_goal_repository(db: SessionDep) -> GoalRepository:
    return GoalRepository(db)


def get_analytics_repository(db: SessionDep) -> AnalyticsRepository:
    return AnalyticsRepository(db)


def get_prediction_repository(db: SessionDep) -> PredictionRepository:
    return PredictionRepository(db)


def get_dataset_repository(db: SessionDep) -> DatasetRepository:
    return DatasetRepository(db)


def get_warehouse_repository(db: SessionDep) -> WarehouseRepository:
    return WarehouseRepository(db)


def get_catalog_repository(db: SessionDep) -> CatalogRepository:
    return CatalogRepository(db)


def get_audit_repository(db: SessionDep) -> AuditRepository:
    return AuditRepository(db)


def get_recommendation_event_repository(db: SessionDep) -> RecommendationEventRepository:
    return RecommendationEventRepository(db)


def get_commission_config_repository(db: SessionDep) -> CommissionConfigRepository:
    return CommissionConfigRepository(db)


def get_cartera360_repository(db: SessionDep) -> Cartera360Repository:
    return Cartera360Repository(db)


def get_notification_repository(db: SessionDep) -> NotificationRepository:
    return NotificationRepository(db)


def get_system_repository(db: SessionDep) -> SystemRepository:
    return SystemRepository(db)


# ── Modelos ML (Singleton vía app.state, cargado en el lifespan de main.py) ──
def get_model_loader(request: Request) -> ModelLoader:
    return request.app.state.model_loader


ModelLoaderDep = Annotated[ModelLoader, Depends(get_model_loader)]


# ── Orquestador de reentrenamiento (Singleton vía app.state, cargado en el lifespan) ──
def get_training_service(request: Request) -> TrainingService:
    return request.app.state.training_service


TrainingServiceDep = Annotated[TrainingService, Depends(get_training_service)]


# ── Servicios ────────────────────────────────────────────────────────────────
def get_user_service(
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
    role_repo: Annotated[RoleRepository, Depends(get_role_repository)],
    catalog_repo: Annotated[CatalogRepository, Depends(get_catalog_repository)],
) -> UserService:
    return UserService(user_repo, role_repo, catalog_repo)


def get_role_service(role_repo: Annotated[RoleRepository, Depends(get_role_repository)]) -> RoleService:
    return RoleService(role_repo)


def get_analytics_service(
    analytics_repo: Annotated[AnalyticsRepository, Depends(get_analytics_repository)],
) -> AnalyticsService:
    return AnalyticsService(analytics_repo)


def get_goals_service(
    goal_repo: Annotated[GoalRepository, Depends(get_goal_repository)],
) -> GoalsService:
    return GoalsService(goal_repo)


def get_prediction_service(
    prediction_repo: Annotated[PredictionRepository, Depends(get_prediction_repository)],
    dataset_repo: Annotated[DatasetRepository, Depends(get_dataset_repository)],
    model_loader: ModelLoaderDep,
    catalog_repo: Annotated[CatalogRepository, Depends(get_catalog_repository)],
    recommendation_event_repo: Annotated[RecommendationEventRepository, Depends(get_recommendation_event_repository)],
) -> PredictionService:
    """Compone también CatalogRepository (enriquecimiento de catálogo) y
    RecommendationEventRepository (telemetría RN-CS2) para el asistente de Venta
    Cruzada por canasta (docs/auditoria/25_modulo_cross_selling.md), además del caso de
    uso original por-cliente."""
    return PredictionService(prediction_repo, dataset_repo, model_loader, catalog_repo, recommendation_event_repo)


def get_warehouse_service(
    warehouse_repo: Annotated[WarehouseRepository, Depends(get_warehouse_repository)],
    dataset_repo: Annotated[DatasetRepository, Depends(get_dataset_repository)],
    model_loader: ModelLoaderDep,
) -> WarehouseService:
    """Módulo Bodega (docs/auditoria/23_modulo_bodega.md): compone el repositorio de
    inventario + `DatasetRepository` (serie de producto para el forecast) + `ModelLoader`
    (reutiliza `demand_rf`, sin modelos nuevos)."""
    return WarehouseService(warehouse_repo, dataset_repo, model_loader)


def get_cartera360_service(
    cartera360_repo: Annotated[Cartera360Repository, Depends(get_cartera360_repository)],
    prediction_service: Annotated[PredictionService, Depends(get_prediction_service)],
    catalog_repo: Annotated[CatalogRepository, Depends(get_catalog_repository)],
) -> Cartera360Service:
    """Módulo Ventas — Cartera de Clientes 360 (docs/features/propuesta_nuevos_modulos_roi.md
    §4, auditoría 32): compone `PredictionService` (churn/RFM/cross-sell ya servidos, sin
    modelos nuevos) con el triage estadístico de `Cartera360Repository`. Definido antes de
    `get_notification_service` porque ese servicio reutiliza `get_lista_trabajo` para el
    generador calculado de churn de Ventas (Fase 4, docs/auditoria/31_modulo_notificaciones.md)."""
    return Cartera360Service(cartera360_repo, prediction_service, catalog_repo)


def get_notification_service(
    notification_repo: Annotated[NotificationRepository, Depends(get_notification_repository)],
    warehouse_service: Annotated[WarehouseService, Depends(get_warehouse_service)],
    prediction_service: Annotated[PredictionService, Depends(get_prediction_service)],
    cartera360_service: Annotated[Cartera360Service, Depends(get_cartera360_service)],
) -> NotificationService:
    """Módulo de Notificaciones (docs/auditoria/31_modulo_notificaciones.md): compone el
    repositorio de notificaciones persistidas con `WarehouseService` (generador calculado de
    Bodega + salud de modelos de Admin), `PredictionService` (desvío de forecast de
    Gerencia, reutiliza `get_sales_forecast`) y `Cartera360Service` (churn alto de la
    cartera propia de Ventas, reutiliza `get_lista_trabajo` -- RLS ya resuelto ahí, RN-V3).
    Sin modelos ML nuevos. Definido antes de `get_goal_ml_service` porque ese servicio la
    inyecta para emitir `metas_generadas` (RN-N2)."""
    return NotificationService(notification_repo, warehouse_service, prediction_service, cartera360_service)


def get_goal_ml_service(
    goal_repo: Annotated[GoalRepository, Depends(get_goal_repository)],
    dataset_repo: Annotated[DatasetRepository, Depends(get_dataset_repository)],
    model_loader: ModelLoaderDep,
    commission_config_repo: Annotated[CommissionConfigRepository, Depends(get_commission_config_repository)],
    notification_service: Annotated[NotificationService, Depends(get_notification_service)],
) -> GoalMLService:
    """Integración ML del módulo Metas y Comisiones (docs/auditoria/15_.../20_...md):
    compone `GoalRepository` + `DatasetRepository` + `ModelLoader` (para `anomaly` y
    `sales_rf`, no para metas -- `goals_rf` fue decomisionado) + `CommissionConfigRepository`
    (ajuste de meta por tipo de vendedor, docs/features/plan_integracion_comisiones_variables.md)
    + `NotificationService` (emite `metas_generadas` a gerencia al final de
    `generate_proposals`, docs/auditoria/31_modulo_notificaciones.md)."""
    return GoalMLService(
        goal_repo, dataset_repo, model_loader,
        commission_config_repo=commission_config_repo, notification_service=notification_service,
    )


def get_audit_service(
    audit_repo: Annotated[AuditRepository, Depends(get_audit_repository)],
) -> AuditService:
    return AuditService(audit_repo)


def get_system_service(
    system_repo: Annotated[SystemRepository, Depends(get_system_repository)],
    model_loader: ModelLoaderDep,
) -> SystemService:
    """Procedencia de datos (docs/auditoria/33_actualizacion_modulo_gerencia.md, H4):
    compone `SystemRepository` (última carga del DW) + `ModelLoader` (estado real de
    los 6 modelos, mismo patrón que `admin_ml.py`)."""
    return SystemService(system_repo, model_loader)


def get_commission_service(
    goal_repo: Annotated[GoalRepository, Depends(get_goal_repository)],
    commission_config_repo: Annotated[CommissionConfigRepository, Depends(get_commission_config_repository)],
) -> CommissionService:
    """Liquidación de comisiones (docs/modulo_metas.md, docs/features/
    plan_integracion_comisiones_variables.md): compone `GoalRepository` (venta real vs.
    meta) + `CommissionConfigRepository` (matriz/crédito/tipo vendedor del esquema
    variable, activo según `settings.COMISION_MODO`)."""
    return CommissionService(goal_repo, commission_config_repo)


def get_commission_simulation_service(
    goal_repo: Annotated[GoalRepository, Depends(get_goal_repository)],
    commission_config_repo: Annotated[CommissionConfigRepository, Depends(get_commission_config_repository)],
) -> CommissionSimulationService:
    return CommissionSimulationService(goal_repo, commission_config_repo)


def get_commission_config_service(
    commission_config_repo: Annotated[CommissionConfigRepository, Depends(get_commission_config_repository)],
    goal_repo: Annotated[GoalRepository, Depends(get_goal_repository)],
) -> CommissionConfigService:
    return CommissionConfigService(commission_config_repo, goal_repo)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]
RoleServiceDep = Annotated[RoleService, Depends(get_role_service)]
AnalyticsServiceDep = Annotated[AnalyticsService, Depends(get_analytics_service)]
GoalsServiceDep = Annotated[GoalsService, Depends(get_goals_service)]
PredictionServiceDep = Annotated[PredictionService, Depends(get_prediction_service)]
GoalMLServiceDep = Annotated[GoalMLService, Depends(get_goal_ml_service)]
CommissionServiceDep = Annotated[CommissionService, Depends(get_commission_service)]
CommissionSimulationServiceDep = Annotated[CommissionSimulationService, Depends(get_commission_simulation_service)]
CommissionConfigServiceDep = Annotated[CommissionConfigService, Depends(get_commission_config_service)]
CommissionConfigRepositoryDep = Annotated[CommissionConfigRepository, Depends(get_commission_config_repository)]
WarehouseServiceDep = Annotated[WarehouseService, Depends(get_warehouse_service)]
AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]
CatalogRepositoryDep = Annotated[CatalogRepository, Depends(get_catalog_repository)]
Cartera360ServiceDep = Annotated[Cartera360Service, Depends(get_cartera360_service)]
NotificationServiceDep = Annotated[NotificationService, Depends(get_notification_service)]
SystemServiceDep = Annotated[SystemService, Depends(get_system_service)]


# ── Resolución de sucursal por rol ────────────────────────────────────────────
def resolve_sucursal_filter(allow_override: bool = True):
    """Fábrica de dependencia: resuelve qué sucursal debe filtrar la consulta según
    el rol del usuario autenticado. Antes esta lógica estaba duplicada copy-pasted en
    6+ endpoints de `analytics.py`.

    - `allow_override=True` (KPIs de gerencia/revenue/catálogos): administrador/gerencia
      pueden pasar `sucursal` por query param (o None = todas); otros roles quedan
      forzados a su propia sucursal, ignorando lo que hayan enviado.
    - `allow_override=False` (bodega/ventas): administrador/gerencia siempre ven todas
      las sucursales (None) sin importar el query param; otros roles quedan forzados a
      la suya. Se preserva esta diferencia exacta del comportamiento original -- no es
      un descuido, es el comportamiento ya validado que tenía cada grupo de endpoints.
    """

    def _resolver(current_user: CurrentUserDep, sucursal: str | None = None) -> str | None:
        es_privilegiado = current_user.role.nombre in ["administrador", "gerencia"]
        if not es_privilegiado:
            return current_user.sucursal
        return sucursal if allow_override else None

    return _resolver


# ── Auditoría de negocio (edw.Fact_Logs_Auditoria) ────────────────────────────
def audit_log(operacion: str = "lectura", tabla_afectada: str = "Consulta_BI", modulo: str = "analytics"):
    """Fábrica de dependencia FastAPI que registra un evento de auditoría de negocio.
    Uso sin cambios respecto a la versión previa: `Depends(audit_log(operacion=...))`."""

    def _log_action(db: SessionDep, current_user: CurrentUserDep):
        AuditRepository(db).log_action(current_user.email, operacion, tabla_afectada, modulo)

    return _log_action
