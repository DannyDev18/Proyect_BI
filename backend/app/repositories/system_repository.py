# backend/app/repositories/system_repository.py
"""Metadatos operativos del sistema (última carga del DW), separados de
`AnalyticsRepository` porque no son un KPI de negocio -- son procedencia de datos
(docs/auditoria/33_actualizacion_modulo_gerencia.md, H4)."""
from datetime import datetime, timedelta
from typing import Any

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

    def get_etl_control_detalle(self) -> list[dict[str, Any]]:
        """Última corrida por tabla destino (panel de salud, Fase 2 Admin, docs/features/
        plan_correcciones_pendientes.md §3) -- a diferencia de `get_ultima_carga_dw`,
        aquí sí importa el detalle por tabla: cuál se sincronizó, cuál falló, cuántas
        filas cargó cada una."""
        rows = self.db.execute(text("""
            SELECT DISTINCT ON (tabla_destino)
                tabla_destino, estado, ultimo_etl_ok, registros_carg, duracion_seg,
                mensaje_error, fecha_ejecucion
            FROM edw.etl_control
            ORDER BY tabla_destino, fecha_ejecucion DESC
        """)).fetchall()
        return [
            {
                "tabla_destino": r[0], "estado": r[1], "ultimo_etl_ok": r[2],
                "registros_cargados": r[3], "duracion_seg": r[4],
                "mensaje_error": r[5], "fecha_ejecucion": r[6],
            }
            for r in rows
        ]

    def get_conteo_logins_fallidos(self, horas: int) -> int:
        """Conteo de `public.intentos_login_fallidos` en la ventana `[ahora - horas,
        ahora]` -- antes no existía ningún registro de intentos fallidos (Fase 2
        Admin, docs/features/plan_correcciones_pendientes.md §3)."""
        limite = datetime.now().astimezone() - timedelta(hours=horas)
        row = self.db.execute(
            text("SELECT COUNT(*) FROM public.intentos_login_fallidos WHERE fecha >= :limite"),
            {"limite": limite},
        ).fetchone()
        return row[0] if row else 0
