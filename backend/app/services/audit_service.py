# backend/app/services/audit_service.py
"""Lectura del log de auditoría (`edw.Fact_Logs_Auditoria`) para el panel de
Administrador (M-02, docs/features/plan_mejoras_proyecto.md) -- reemplaza el mock
`AUDIT_ENTRIES` del frontend. El hecho no tiene columna de severidad; se infiere aquí
de `tipo_operacion` (capa de negocio, no de acceso a datos)."""
from app.repositories.audit_repository import AuditRepository

_NIVEL_POR_OPERACION = {
    "DELETE": "ERROR",
    "UPDATE": "WARN",
}


class AuditService:
    def __init__(self, audit_repo: AuditRepository):
        self.audit_repo = audit_repo

    def get_recent_logs(self, limit: int = 50) -> list[dict]:
        rows = self.audit_repo.get_recent(limit=limit)
        return [
            {
                "ts": row["fecha_carga"].strftime("%Y-%m-%d %H:%M:%S") if row["fecha_carga"] else "",
                "level": _NIVEL_POR_OPERACION.get((row["tipo_operacion"] or "").upper(), "INFO"),
                "source": row["modulo"] or "desconocido",
                "msg": f"{row['tipo_operacion']} sobre {row['tabla_afectada']}"
                + (f" (usuario: {row['codusu']})" if row["codusu"] else ""),
            }
            for row in rows
        ]
