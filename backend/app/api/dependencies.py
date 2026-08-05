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
from app.repositories.meta_config_modulo_repository import MetaConfigModuloRepository
from app.inventory import (
    ReplenishmentConfigRepository,
    ReplenishmentConfigService,
    ReplenishmentProposalRepository,
    ReplenishmentService,
)
from app.repositories.meta_config_repository import MetaConfigRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.ml_model_run_repository import MLModelRunRepository
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
from app.services.cross_sell_engine_service import CrossSellEngineService
from app.services.gestion_service import GestionService
from app.services.goal_ml_service import GoalMLService
from app.services.goals_service import GoalsService
from app.services.meta_config_modulo_service import MetaConfigModuloService
from app.services.meta_config_service import MetaConfigService
from app.services.notification_service import NotificationService
from app.services.prediction_service import PredictionService
from app.services.role_service import RoleService
from app.services.system_service import SystemService
from app.services.training_service import TrainingService
from app.services.user_service import UserService
from app.services.vendor_dashboard_service import VendorDashboardService
from app.services.warehouse_service import WarehouseService


# ── Repositorios ─────────────────────────────────────────────────────────────
def get_user_repository(db: SessionDep) -> UserRepository:
    return UserRepository(db)


def get_role_repository(db: SessionDep) -> RoleRepository:
    return RoleRepository(db)


def get_goal_repository(db: SessionDep) -> GoalRepository:
    return GoalRepository(db)


def get_meta_config_repository(db: SessionDep) -> MetaConfigRepository:
    return MetaConfigRepository(db)


def get_analytics_repository(db: SessionDep) -> AnalyticsRepository:
    return AnalyticsRepository(db)


def get_prediction_repository(db: SessionDep) -> PredictionRepository:
    return PredictionRepository(db)


def get_dataset_repository(db: SessionDep) -> DatasetRepository:
    return DatasetRepository(db)


# ── RLS por bodega (RN-B10, docs/features/plan_correcciones_integrales_sistema.md
# Fase 1.b) ─────────────────────────────────────────────────────────────────────
def resolve_almacenes_filter(current_user: CurrentUserDep) -> list[str] | None:
    """Restricción de seguridad -- NO confundir con el filtro `almacen` que el usuario
    elige en la barra de filtros del dashboard. Esta lista viene de lo que el admin le
    asignó a la cuenta (public.usuario_almacenes) y `WarehouseRepository` la intersecta
    con lo que el usuario pida, nunca la deja ampliar el conjunto (H-1, fuga de datos
    entre bodegas). `None` = sin restricción (gerencia/administrador, o rol bodega con
    `todos_los_almacenes=True`); `[]` = rol bodega sin ninguna bodega asignada (no debe
    ver ningún dato, no "todos" -- ver B-2 del plan)."""
    if current_user.role.nombre != "bodega":
        return None
    if current_user.todos_los_almacenes:
        return None
    return current_user.codalms


def get_warehouse_repository(
    db: SessionDep,
    almacenes_permitidos: Annotated[list[str] | None, Depends(resolve_almacenes_filter)],
) -> WarehouseRepository:
    return WarehouseRepository(db, almacenes_permitidos=almacenes_permitidos)


def get_catalog_repository(db: SessionDep) -> CatalogRepository:
    return CatalogRepository(db)


def get_replenishment_config_repository(db: SessionDep) -> ReplenishmentConfigRepository:
    return ReplenishmentConfigRepository(db)


def get_replenishment_proposal_repository(db: SessionDep) -> ReplenishmentProposalRepository:
    return ReplenishmentProposalRepository(db)


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


def get_ml_model_run_repository(db: SessionDep) -> MLModelRunRepository:
    return MLModelRunRepository(db)


MLModelRunRepositoryDep = Annotated[MLModelRunRepository, Depends(get_ml_model_run_repository)]


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
    catalog_repo: Annotated[CatalogRepository, Depends(get_catalog_repository)],
) -> GoalsService:
    return GoalsService(goal_repo, catalog_repo)


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


def get_replenishment_config_service(
    config_repo: Annotated[ReplenishmentConfigRepository, Depends(get_replenishment_config_repository)],
) -> ReplenishmentConfigService:
    return ReplenishmentConfigService(config_repo)


def get_replenishment_service(
    warehouse_repo: Annotated[WarehouseRepository, Depends(get_warehouse_repository)],
    config_repo: Annotated[ReplenishmentConfigRepository, Depends(get_replenishment_config_repository)],
    proposal_repo: Annotated[ReplenishmentProposalRepository, Depends(get_replenishment_proposal_repository)],
) -> ReplenishmentService:
    """Módulo Reabastecimiento Inteligente (docs/features/plan_reabastecimiento_
    inteligente.md): reutiliza `WarehouseRepository` (misma RLS por almacén, RN-B10,
    que el resto de Bodega) + la configuración editable de política/lead time +
    `ReplenishmentProposalRepository` (F9, propuestas de compra persistidas)."""
    return ReplenishmentService(warehouse_repo, config_repo, proposal_repo)


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


def get_cross_sell_engine_service(
    cartera360_repo: Annotated[Cartera360Repository, Depends(get_cartera360_repository)],
    catalog_repo: Annotated[CatalogRepository, Depends(get_catalog_repository)],
    prediction_service: Annotated[PredictionService, Depends(get_prediction_service)],
) -> CrossSellEngineService:
    """Motor compuesto de Venta Cruzada (docs/features/plan_refactor_venta_cruzada_ia.md
    §3, decisión 1): consume `PredictionService` por inyección en vez de engordarlo,
    mismo patrón que `get_cartera360_service`. `Cartera360Repository` aporta el CLV
    histórico/agregados de cliente único (Fase 1); en la Fase 2 este mismo servicio
    ganará el ranker sin crear un servicio nuevo distinto."""
    return CrossSellEngineService(cartera360_repo, catalog_repo, prediction_service)


def get_gestion_service(
    cartera360_repo: Annotated[Cartera360Repository, Depends(get_cartera360_repository)],
    catalog_repo: Annotated[CatalogRepository, Depends(get_catalog_repository)],
) -> GestionService:
    """"Mi Ruta Inteligente de Ventas" (docs/features/plan_refactor_cartera360_ruta_
    inteligente.md §2.1): escritura/trazabilidad de gestión, separado de
    `Cartera360Service` (lectura/priorización) -- mismo patrón de división que
    `CrossSellEngineService` vs. `PredictionService`."""
    return GestionService(cartera360_repo, catalog_repo)


def get_commission_simulation_service(
    goal_repo: Annotated[GoalRepository, Depends(get_goal_repository)],
    commission_config_repo: Annotated[CommissionConfigRepository, Depends(get_commission_config_repository)],
    catalog_repo: Annotated[CatalogRepository, Depends(get_catalog_repository)],
) -> CommissionSimulationService:
    """Definido antes de `get_notification_service` (igual que `get_cartera360_service`
    arriba): ese servicio la inyecta para el generador calculado de divergencia
    plano vs. variable del piloto en sombra (Fase 2 ítem 3, docs/features/
    plan_actualizacion_modulo_metas_comisiones.md). `catalog_repo` es para
    `proyectar_comision_variable` (enriquecimiento de nombre de vendedor)."""
    return CommissionSimulationService(goal_repo, commission_config_repo, catalog_repo)


def get_notification_service(
    notification_repo: Annotated[NotificationRepository, Depends(get_notification_repository)],
    warehouse_service: Annotated[WarehouseService, Depends(get_warehouse_service)],
    cartera360_service: Annotated[Cartera360Service, Depends(get_cartera360_service)],
    commission_simulation_service: Annotated[CommissionSimulationService, Depends(get_commission_simulation_service)],
    replenishment_service: Annotated[ReplenishmentService, Depends(get_replenishment_service)],
) -> NotificationService:
    """Módulo de Notificaciones (docs/auditoria/31_modulo_notificaciones.md): compone el
    repositorio de notificaciones persistidas con `WarehouseService` (generador calculado de
    Bodega + salud de modelos de Admin), `Cartera360Service` (churn alto de la
    cartera propia de Ventas, reutiliza `get_lista_trabajo` -- RLS ya resuelto ahí, RN-V3),
    `CommissionSimulationService` (divergencia plano vs variable del piloto en sombra,
    Fase 2 ítem 3 de plan_actualizacion_modulo_metas_comisiones.md -- reutiliza `simular`,
    el mismo cálculo que ya sirve `POST /commission-simulation`) y `ReplenishmentService`
    (F7 de docs/features/plan_reabastecimiento_inteligente.md: cambio brusco de demanda y
    tendencia decreciente sostenida -- las 2 señales que el generador de Bodega nunca
    calculó; el riesgo de quiebre y el sobrestock NO se duplican aquí, ver docstring de
    `ReplenishmentService.get_alertas`). Sin modelos ML nuevos. (`PredictionService` se
    retiró de esta composición junto con el desvío de forecast de Gerencia, auditoría 49.)
    Definido antes de `get_goal_ml_service` porque ese servicio la inyecta para emitir
    `metas_generadas` (RN-N2)."""
    return NotificationService(
        notification_repo, warehouse_service, cartera360_service,
        commission_simulation_service, replenishment_service,
    )


def get_meta_config_service(
    meta_config_repo: Annotated[MetaConfigRepository, Depends(get_meta_config_repository)],
) -> MetaConfigService:
    return MetaConfigService(meta_config_repo)


def get_meta_config_modulo_repository(db: SessionDep) -> MetaConfigModuloRepository:
    return MetaConfigModuloRepository(db)


def get_meta_config_modulo_service(
    meta_config_modulo_repo: Annotated[MetaConfigModuloRepository, Depends(get_meta_config_modulo_repository)],
) -> MetaConfigModuloService:
    return MetaConfigModuloService(meta_config_modulo_repo)


def get_goal_ml_service(
    goal_repo: Annotated[GoalRepository, Depends(get_goal_repository)],
    dataset_repo: Annotated[DatasetRepository, Depends(get_dataset_repository)],
    model_loader: ModelLoaderDep,
    commission_config_repo: Annotated[CommissionConfigRepository, Depends(get_commission_config_repository)],
    notification_service: Annotated[NotificationService, Depends(get_notification_service)],
    meta_config_modulo_service: Annotated[MetaConfigModuloService, Depends(get_meta_config_modulo_service)],
) -> GoalMLService:
    """Integración ML del módulo Metas y Comisiones (docs/auditoria/15_.../20_.../
    46_motor_metas_configurable.md): compone `GoalRepository` + `DatasetRepository` +
    `ModelLoader` (para `association`, no para metas -- `goals_rf` fue decomisionado)
    + `CommissionConfigRepository` (ajuste de meta por tipo de vendedor,
    docs/features/plan_integracion_comisiones_variables.md) + `NotificationService`
    (emite `metas_generadas` a gerencia al final de `generate_proposals`, docs/auditoria/
    31_modulo_notificaciones.md) + la configuración modular del motor v3 (docs/features/
    plan_motor_metas_v3_y_comisiones_unificadas.md §9, Fase 6 -- reemplaza a
    `MetaConfigService`/`metas_config_parametros` como fuente real, resuelta UNA VEZ por
    request, no una consulta por vendedor dentro de `generate_proposals`)."""
    motor_parametros, pipeline_config = meta_config_modulo_service.get_pipeline_config()
    return GoalMLService(
        goal_repo, dataset_repo, model_loader,
        commission_config_repo=commission_config_repo, notification_service=notification_service,
        meta_motor_parametros=motor_parametros, pipeline_config=pipeline_config,
    )


def get_audit_service(
    audit_repo: Annotated[AuditRepository, Depends(get_audit_repository)],
) -> AuditService:
    return AuditService(audit_repo)


def get_system_service(
    system_repo: Annotated[SystemRepository, Depends(get_system_repository)],
    model_loader: ModelLoaderDep,
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
    catalog_repo: Annotated[CatalogRepository, Depends(get_catalog_repository)],
) -> SystemService:
    """Procedencia de datos (docs/auditoria/33_actualizacion_modulo_gerencia.md, H4):
    compone `SystemRepository` (última carga del DW) + `ModelLoader` (estado real de
    los 4 modelos, mismo patrón que `admin_ml.py`). Fase 5 §5.5 suma `UserRepository`/
    `CatalogRepository` para el resumen de métricas del dashboard de Admin."""
    return SystemService(system_repo, model_loader, user_repo, catalog_repo)


def get_commission_service(
    goal_repo: Annotated[GoalRepository, Depends(get_goal_repository)],
    commission_config_repo: Annotated[CommissionConfigRepository, Depends(get_commission_config_repository)],
    catalog_repo: Annotated[CatalogRepository, Depends(get_catalog_repository)],
) -> CommissionService:
    """Liquidación de comisiones (docs/modulo_metas.md, docs/features/
    plan_integracion_comisiones_variables.md): compone `GoalRepository` (venta real vs.
    meta) + `CommissionConfigRepository` (matriz/crédito/tipo vendedor del esquema
    variable, activo según `settings.COMISION_MODO`) + `CatalogRepository` (estado
    activo/inactivo del vendedor, para filtrar el panel "Cumplimiento real y comisión
    por vendedor")."""
    return CommissionService(goal_repo, commission_config_repo, catalog_repo)


def get_commission_config_service(
    commission_config_repo: Annotated[CommissionConfigRepository, Depends(get_commission_config_repository)],
    goal_repo: Annotated[GoalRepository, Depends(get_goal_repository)],
    catalog_repo: Annotated[CatalogRepository, Depends(get_catalog_repository)],
) -> CommissionConfigService:
    return CommissionConfigService(commission_config_repo, goal_repo, catalog_repo)


def get_vendor_dashboard_service(
    analytics_service: Annotated[AnalyticsService, Depends(get_analytics_service)],
    commission_service: Annotated[CommissionService, Depends(get_commission_service)],
    cartera360_service: Annotated[Cartera360Service, Depends(get_cartera360_service)],
    gestion_service: Annotated[GestionService, Depends(get_gestion_service)],
    catalog_repo: Annotated[CatalogRepository, Depends(get_catalog_repository)],
) -> VendorDashboardService:
    """Dashboard "Mi Negocio" del vendedor (auditoría 43, Fase 5): compone servicios ya
    existentes -- sin lógica de negocio nueva de comisiones ni de cartera, mismo criterio
    de composición por inyección que `CrossSellEngineService`/`Cartera360Service`."""
    return VendorDashboardService(analytics_service, commission_service, cartera360_service, gestion_service, catalog_repo)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]
RoleServiceDep = Annotated[RoleService, Depends(get_role_service)]
AnalyticsServiceDep = Annotated[AnalyticsService, Depends(get_analytics_service)]
GoalsServiceDep = Annotated[GoalsService, Depends(get_goals_service)]
PredictionServiceDep = Annotated[PredictionService, Depends(get_prediction_service)]
GoalMLServiceDep = Annotated[GoalMLService, Depends(get_goal_ml_service)]
MetaConfigServiceDep = Annotated[MetaConfigService, Depends(get_meta_config_service)]
MetaConfigModuloServiceDep = Annotated[MetaConfigModuloService, Depends(get_meta_config_modulo_service)]
CommissionServiceDep = Annotated[CommissionService, Depends(get_commission_service)]
CommissionSimulationServiceDep = Annotated[CommissionSimulationService, Depends(get_commission_simulation_service)]
CommissionConfigServiceDep = Annotated[CommissionConfigService, Depends(get_commission_config_service)]
VendorDashboardServiceDep = Annotated[VendorDashboardService, Depends(get_vendor_dashboard_service)]
CommissionConfigRepositoryDep = Annotated[CommissionConfigRepository, Depends(get_commission_config_repository)]
WarehouseServiceDep = Annotated[WarehouseService, Depends(get_warehouse_service)]
ReplenishmentServiceDep = Annotated[ReplenishmentService, Depends(get_replenishment_service)]
ReplenishmentConfigServiceDep = Annotated[ReplenishmentConfigService, Depends(get_replenishment_config_service)]
AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]
CatalogRepositoryDep = Annotated[CatalogRepository, Depends(get_catalog_repository)]
Cartera360ServiceDep = Annotated[Cartera360Service, Depends(get_cartera360_service)]
CrossSellEngineServiceDep = Annotated[CrossSellEngineService, Depends(get_cross_sell_engine_service)]
GestionServiceDep = Annotated[GestionService, Depends(get_gestion_service)]
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
