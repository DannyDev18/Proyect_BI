# backend/app/api/routes/admin.py
"""Administrador: detección de fraude/anomalías operativas. Router propio (no vive en
`sales.py`) porque agrupa por audiencia/permiso (solo administrador), no por dominio
de negocio -- ya vivía bajo el prefijo /admin/ antes del refactor."""
from datetime import date

from fastapi import APIRouter, Depends

from app.api.dependencies import AuditServiceDep, NotificationServiceDep, PredictionServiceDep, audit_log
from app.core.deps import PermissionChecker
from app.schemas.analytics import AnomaliaResponse, AuditLogEntryResponse
from app.schemas.pagination import Page, PaginationParams, pagination_params

router = APIRouter()

admin_only = PermissionChecker(allowed_roles=["administrador"])


@router.get(
    "/anomalies", response_model=AnomaliaResponse, dependencies=[Depends(admin_only)],
)
def detect_transactional_anomaly(
    transaccion_id: str,
    prediction_service: PredictionServiceDep,
    notification_service: NotificationServiceDep,
    _audit: None = Depends(audit_log(operacion="PREDICT", tabla_afectada="fact_ventas_detalle", modulo="detect_fraude")),
) -> AnomaliaResponse:
    """Ejecuta el modelo Isolation Forest sobre una transacción para calificarla como anomalía.
    Si resulta anómala, emite una notificación persistida a administrador (RN-N2,
    docs/auditoria/31_modulo_notificaciones.md) -- el dedupe de 24h evita reinsertar la
    misma alerta si la transacción se vuelve a consultar."""
    res = prediction_service.get_anomaly_status(transaccion_id)
    if res["es_anomalia"]:
        notification_service.emitir(
            tipo_evento="anomalia_detectada",
            rol_destino="administrador",
            titulo="Anomalía detectada",
            mensaje=f"🚨 La transacción {transaccion_id} fue calificada como anómala (score={res['score']:.4f}).",
            prioridad="alta",
            accion_url="/admin",
            contexto={"transaccion_id": transaccion_id},
        )
    return AnomaliaResponse(transaccion_id=transaccion_id, score=res["score"], es_anomalia=res["es_anomalia"])


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
