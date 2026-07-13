# backend/app/repositories/audit_repository.py
"""ÚNICA excepción documentada a la regla "el backend no escribe en edw.*": el log de
auditoría de negocio (`edw.Fact_Logs_Auditoria`) ya vivía en ese esquema antes de este
refactor. Cambiarlo de esquema es una decisión de infraestructura de datos (DDL/ETL),
fuera de alcance de un refactor de arquitectura de código -- se documenta aquí en vez
de silenciarlo."""
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("Backend.AuditRepository")


class AuditRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """Últimos eventos de `edw.Fact_Logs_Auditoria` (M-02, DashboardAdmin real en vez
        de mocks). No hay columna de severidad en el hecho -- se infiere de
        `tipo_operacion` en el servicio, no aquí (esta capa solo trae datos crudos)."""
        rows = self.db.execute(
            text("""
                SELECT
                    fla.fecha_carga,
                    fla.tipo_operacion,
                    fla.tabla_afectada,
                    fla.modulo,
                    du.codusu
                FROM edw.Fact_Logs_Auditoria fla
                LEFT JOIN edw.dim_usuario du ON du.usuario_sk = fla.usuario_sk
                ORDER BY fla.log_sk DESC
                LIMIT :limit
            """),
            {"limit": limit},
        ).fetchall()

        return [
            {
                "fecha_carga": r[0],
                "tipo_operacion": r[1],
                "tabla_afectada": r[2],
                "modulo": r[3],
                "codusu": r[4],
            }
            for r in rows
        ]

    def log_action(self, username: str, operacion: str, tabla_afectada: str, modulo: str) -> None:
        try:
            user_row = self.db.execute(
                text("SELECT usuario_sk FROM edw.dim_usuario WHERE codusu = :username LIMIT 1;"),
                {"username": username},
            ).fetchone()
            usuario_sk = user_row[0] if user_row else 1

            sucursal_sk = 1  # Por defecto matriz (mismo comportamiento previo, sin resolver por usuario)

            fecha_sk = self.db.execute(text("""
                SELECT COALESCE(
                    (SELECT fecha_sk FROM edw.dim_fecha WHERE fecha_sk = CAST(TO_CHAR(NOW(), 'YYYYMMDD') AS INT)),
                    (SELECT MAX(fecha_sk) FROM edw.dim_fecha)
                );
            """)).fetchone()[0]

            self.db.execute(
                text("""
                    INSERT INTO edw.Fact_Logs_Auditoria
                    (fecha_sk, usuario_sk, sucursal_sk, tabla_afectada, tipo_operacion, modulo)
                    VALUES (:f_sk, :u_sk, :s_sk, :tabla, :oper, :mod)
                """),
                {
                    "f_sk": fecha_sk, "u_sk": usuario_sk, "s_sk": sucursal_sk,
                    "tabla": tabla_afectada[:80], "oper": operacion[:10], "mod": modulo[:20],
                },
            )
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            # Best-effort intencional: un fallo de auditoría no debe tumbar la request
            # que la disparó (ver api/dependencies.py -- se usa como dependencia FastAPI).
            logger.error(f"Fallo al escribir auditoría en el DW: {e}")
