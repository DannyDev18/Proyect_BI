# backend/app/core/audit.py
import logging
from typing import Callable
from fastapi import Request
from sqlalchemy import text
from app.core.deps import SessionDep, CurrentUserDep

logger = logging.getLogger("Backend.Audit")

def audit_log(operacion: str = "lectura", tabla_afectada: str = "Consulta_BI", modulo: str = "analytics") -> Callable:
    """
    Dependencia de FastAPI para inyectar un log de auditoría en el Data Warehouse.
    Registra el nombre de usuario, fecha, operación y módulo.
    """
    def _log_action(
        request: Request,
        db: SessionDep,
        current_user: CurrentUserDep,
    ):
        try:
            # Intentar resolver usuario_sk mapeando username a codusu en la dimension
            # Si no, fallback a un usuario ID "0" o "1"
            sk_query = """
                SELECT usuario_sk
                FROM edw.dim_usuario
                WHERE codusu = :username
                LIMIT 1;
            """
            user_data = db.execute(text(sk_query), {"username": current_user.email}).fetchone()
            usuario_sk = user_data[0] if user_data else 1
            
            # Asignar sucursal desde el rol o por defecto
            sucursal_sk = 1 # Por defecto matriz
            
            fecha_sk_query = """
                SELECT COALESCE(
                    (SELECT fecha_sk FROM edw.dim_fecha WHERE fecha_sk = CAST(TO_CHAR(NOW(), 'YYYYMMDD') AS INT)),
                    (SELECT MAX(fecha_sk) FROM edw.dim_fecha)
                );
            """
            fecha_sk = db.execute(text(fecha_sk_query)).fetchone()[0]

            insert_q = """
                INSERT INTO edw.Fact_Logs_Auditoria
                (fecha_sk, usuario_sk, sucursal_sk, tabla_afectada, tipo_operacion, modulo)
                VALUES
                (:f_sk, :u_sk, :s_sk, :tabla, :oper, :mod)
            """
            
            db.execute(
                text(insert_q),
                {
                    "f_sk": fecha_sk,
                    "u_sk": usuario_sk,
                    "s_sk": sucursal_sk,
                    "tabla": tabla_afectada[:80],
                    "oper": operacion[:10],
                    "mod": modulo[:20]
                }
            )
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Fallo escribir auditoria DW: {e}")
            
    return _log_action
