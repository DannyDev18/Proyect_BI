# backend/app/services/audit_service.py
"""Lectura del log de auditoría (`edw.Fact_Logs_Auditoria`) para el panel de
Administrador (M-02, docs/features/plan_mejoras_proyecto.md) -- reemplaza el mock
`AUDIT_ENTRIES` del frontend. El hecho no tiene columna de severidad; se infiere aquí
de `tipo_operacion` (capa de negocio, no de acceso a datos)."""
from datetime import date, timedelta

from app.core.config import settings
from app.repositories.audit_repository import AuditRepository
from app.schemas.pagination import Page, PaginationParams, paginar

_NIVEL_POR_OPERACION = {
    "DELETE": "ERROR",
    "UPDATE": "WARN",
}

# Fetch acotado antes de paginar en memoria (mismo patrón de Bodega/auditoría 24):
# suficiente para cubrir varias páginas sin traer el histórico completo.
_FETCH_LIMIT = 2000


class AuditService:
    def __init__(self, audit_repo: AuditRepository):
        self.audit_repo = audit_repo

    def get_recent_logs(
        self,
        pagination: PaginationParams,
        fecha_desde: date | None = None,
        fecha_hasta: date | None = None,
        usuario: str | None = None,
        modulo: str | None = None,
    ) -> Page[dict]:
        """Docs/auditoria/36_actualizacion_modulo_admin.md (H2): filtros de fecha/
        usuario/módulo + paginación `Page[T]`. Sin `fecha_desde`, se acota a los
        últimos `ADMIN_AUDIT_LOGS_VENTANA_DIAS` (default 30) en vez de todo el
        histórico."""
        desde_efectivo = fecha_desde or (date.today() - timedelta(days=settings.ADMIN_AUDIT_LOGS_VENTANA_DIAS))
        rows = self.audit_repo.get_recent(
            fecha_desde=desde_efectivo, fecha_hasta=fecha_hasta,
            usuario=usuario, modulo=modulo, limit=_FETCH_LIMIT,
        )
        entradas = [
            {
                "ts": row["fecha_carga"].strftime("%Y-%m-%d %H:%M:%S") if row["fecha_carga"] else "",
                "level": _NIVEL_POR_OPERACION.get((row["tipo_operacion"] or "").upper(), "INFO"),
                "source": row["modulo"] or "desconocido",
                "msg": f"{row['tipo_operacion']} sobre {row['tabla_afectada']}"
                + (f" (usuario: {row['codusu']})" if row["codusu"] else ""),
            }
            for row in rows
        ]
        return paginar(entradas, pagination)
