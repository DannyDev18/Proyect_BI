# backend/app/repositories/system_repository.py
"""Metadatos operativos del sistema (última carga del DW), separados de
`AnalyticsRepository` porque no son un KPI de negocio -- son procedencia de datos
(docs/auditoria/33_actualizacion_modulo_gerencia.md, H4)."""
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session


class SystemRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_ultima_carga_dw(self) -> datetime | None:
        """Último `edw.etl_control.ultimo_etl_ok` con `estado='SUCCESS'`, sin importar
        la tabla destino -- la barra de procedencia solo necesita "¿cuándo se sincronizó
        el DW por última vez?", no el detalle por tabla."""
        row = self.db.execute(
            text("SELECT MAX(ultimo_etl_ok) FROM edw.etl_control WHERE estado = 'SUCCESS'")
        ).fetchone()
        return row[0] if row else None
