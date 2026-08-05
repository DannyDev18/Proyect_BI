# backend/app/api/routes/admin.py
"""Administrador: métricas operativas, auditoría y salud del sistema. Router propio (no
vive en `sales.py`) porque agrupa por audiencia/permiso (solo administrador), no por
dominio de negocio -- ya vivía bajo el prefijo /admin/ antes del refactor.

El detector de anomalías transaccionales (Isolation Forest) que vivía aquí fue
decomisionado por completo (docs/auditoria/51_decomision_anomaly_y_churn_unico.md),
mismo criterio que sales_rf/goals_rf: sin reemplazo, no solo ocultado en el frontend."""
from datetime import date

from fastapi import APIRouter, Depends

from app.api.dependencies import AuditServiceDep, SystemServiceDep
from app.core.deps import PermissionChecker
from app.schemas.analytics import AuditLogEntryResponse
from app.schemas.pagination import Page, PaginationParams, pagination_params
from app.schemas.system import AdminResumenResponse, SystemHealthResponse

router = APIRouter()

admin_only = PermissionChecker(allowed_roles=["administrador"])


@router.get(
    "/resumen", response_model=AdminResumenResponse, dependencies=[Depends(admin_only)],
)
def get_admin_resumen(system_service: SystemServiceDep) -> AdminResumenResponse:
    """Métricas reales del dashboard de Admin (Fase 5 §5.5, docs/features/
    plan_correcciones_integrales_sistema.md): usuarios activos/inactivos, vendedores y
    bodegas vigentes del EDW."""
    return AdminResumenResponse(**system_service.get_admin_resumen())


@router.get(
    "/system-health", response_model=SystemHealthResponse, dependencies=[Depends(admin_only)],
)
def get_system_health(system_service: SystemServiceDep) -> SystemHealthResponse:
    """Panel de salud del sistema (Fase 2 Admin, docs/features/
    plan_correcciones_pendientes.md §3): detalle por tabla de `edw.etl_control` (última
    corrida, filas, errores) + conteo de logins fallidos recientes. Complementa
    `GET /system/provenance` (visible a los 4 roles, solo el resumen global) con el
    detalle operativo que únicamente administrador debe ver."""
    return SystemHealthResponse(**system_service.get_system_health())


@router.get(
    "/audit-logs", response_model=Page[AuditLogEntryResponse], dependencies=[Depends(admin_only)],
)
def get_audit_logs(
    audit_service: AuditServiceDep,
    pagination: PaginationParams = Depends(pagination_params),
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    usuario: str | None = None,
    modulo: str | None = None,
) -> Page[AuditLogEntryResponse]:
    """Eventos de `edw.Fact_Logs_Auditoria` (M-02: reemplaza el mock `AUDIT_ENTRIES` del
    `DashboardAdmin`). Filtrable por fecha/usuario/módulo y paginado (docs/auditoria/
    36_actualizacion_modulo_admin.md, H2) -- sin `fecha_desde`, se acota a
    `ADMIN_AUDIT_LOGS_VENTANA_DIAS` en vez de todo el histórico."""
    pagina = audit_service.get_recent_logs(
        pagination, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, usuario=usuario, modulo=modulo,
    )
    return Page(
        items=[AuditLogEntryResponse(**entry) for entry in pagina.items],
        total=pagina.total, page=pagina.page, page_size=pagina.page_size, total_pages=pagina.total_pages,
    )
