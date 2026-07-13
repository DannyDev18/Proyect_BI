# backend/app/api/routes/admin.py
"""Administrador: detección de fraude/anomalías operativas. Router propio (no vive en
`sales.py`) porque agrupa por audiencia/permiso (solo administrador), no por dominio
de negocio -- ya vivía bajo el prefijo /admin/ antes del refactor."""
from fastapi import APIRouter, Depends

from app.api.dependencies import AuditServiceDep, PredictionServiceDep, audit_log
from app.core.deps import PermissionChecker
from app.schemas.analytics import AnomaliaResponse, AuditLogEntryResponse

router = APIRouter()

admin_only = PermissionChecker(allowed_roles=["administrador"])


@router.get(
    "/anomalies", response_model=AnomaliaResponse, dependencies=[Depends(admin_only)],
)
def detect_transactional_anomaly(
    transaccion_id: str,
    prediction_service: PredictionServiceDep,
    _audit: None = Depends(audit_log(operacion="PREDICT", tabla_afectada="fact_ventas_detalle", modulo="detect_fraude")),
) -> AnomaliaResponse:
    """Ejecuta el modelo Isolation Forest sobre una transacción para calificarla como anomalía."""
    res = prediction_service.get_anomaly_status(transaccion_id)
    return AnomaliaResponse(transaccion_id=transaccion_id, score=res["score"], es_anomalia=res["es_anomalia"])


@router.get(
    "/audit-logs", response_model=list[AuditLogEntryResponse], dependencies=[Depends(admin_only)],
)
def get_audit_logs(audit_service: AuditServiceDep, limit: int = 50) -> list[AuditLogEntryResponse]:
    """Últimos eventos de `edw.Fact_Logs_Auditoria` (M-02: reemplaza el mock
    `AUDIT_ENTRIES` del `DashboardAdmin`)."""
    return [AuditLogEntryResponse(**entry) for entry in audit_service.get_recent_logs(limit=limit)]
