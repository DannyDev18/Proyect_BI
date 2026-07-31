# backend/tests/unit/test_audit_service.py
"""AuditService probado con repositorio mockeado (docs/auditoria/
36_actualizacion_modulo_admin.md, H2): filtros de fecha/usuario/módulo +
paginación en memoria. Ningún test toca la BD."""
from datetime import date
from unittest.mock import MagicMock

from app.core.config import settings
from app.schemas.pagination import PaginationParams
from app.services.audit_service import AuditService


def _row(tipo="INSERT", tabla="tabla_x", modulo="analytics", codusu="U1"):
    return {"fecha_carga": date(2026, 7, 1), "tipo_operacion": tipo, "tabla_afectada": tabla, "modulo": modulo, "codusu": codusu}


def test_get_recent_logs_usa_ventana_por_defecto_sin_fecha_desde():
    repo = MagicMock()
    repo.get_recent.return_value = []
    service = AuditService(repo)

    service.get_recent_logs(PaginationParams(page=1, page_size=25))

    kwargs = repo.get_recent.call_args.kwargs
    assert kwargs["fecha_desde"] == date.today() - __import__("datetime").timedelta(days=settings.ADMIN_AUDIT_LOGS_VENTANA_DIAS)


def test_get_recent_logs_propaga_fecha_desde_explicita():
    repo = MagicMock()
    repo.get_recent.return_value = []
    service = AuditService(repo)
    explicita = date(2026, 1, 1)

    service.get_recent_logs(PaginationParams(page=1, page_size=25), fecha_desde=explicita)

    assert repo.get_recent.call_args.kwargs["fecha_desde"] == explicita


def test_get_recent_logs_pagina_en_memoria():
    repo = MagicMock()
    repo.get_recent.return_value = [_row(codusu=f"U{i}") for i in range(5)]
    service = AuditService(repo)

    pagina = service.get_recent_logs(PaginationParams(page=1, page_size=2))

    assert pagina.total == 5
    assert pagina.page_size == 2
    assert len(pagina.items) == 2


def test_get_recent_logs_infiere_nivel_por_operacion():
    repo = MagicMock()
    repo.get_recent.return_value = [_row(tipo="DELETE"), _row(tipo="UPDATE"), _row(tipo="INSERT")]
    service = AuditService(repo)

    pagina = service.get_recent_logs(PaginationParams(page=1, page_size=10))

    niveles = [item["level"] for item in pagina.items]
    assert niveles == ["ERROR", "WARN", "INFO"]
