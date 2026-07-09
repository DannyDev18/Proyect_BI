# backend/app/repositories/audit_repository.py
"""ÚNICA excepción documentada a la regla "el backend no escribe en edw.*": el log de
auditoría de negocio (`edw.Fact_Logs_Auditoria`) ya vivía en ese esquema antes de este
refactor. Cambiarlo de esquema es una decisión de infraestructura de datos (DDL/ETL),
fuera de alcance de un refactor de arquitectura de código -- se documenta aquí en vez
de silenciarlo."""
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("Backend.AuditRepository")


class AuditRepository:
    def __init__(self, db: Session):
        self.db = db

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
