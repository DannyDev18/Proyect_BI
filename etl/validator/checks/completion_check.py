# checks/completion_check.py
"""Gate de Nivel 1: ¿el ETL terminó exitosamente para esta tabla en el rango pedido?

Se ejecuta ANTES que cualquier otro check. Si no hay una corrida SUCCESS reciente en
edw.etl_control, no tiene sentido comparar sumatorias contra una carga incompleta o inexistente.
"""
from sqlalchemy import text

from validator.models.result_types import CheckResult, Severity


def run_completion_check(pg_engine, tabla_edw: str, fecha_desde: str) -> CheckResult:
    sql = text("""
        SELECT estado, ultimo_etl_ok, registros_carg, mensaje_error
        FROM edw.etl_control
        WHERE tabla_destino = :tabla
        ORDER BY fecha_ejecucion DESC
        LIMIT 1
    """)
    with pg_engine.begin() as conn:
        row = conn.execute(sql, {"tabla": tabla_edw}).mappings().first()

    if row is None:
        return CheckResult(
            check_name="completion_check",
            severity=Severity.CRITICAL,
            descripcion=f"No existe ninguna corrida registrada en edw.etl_control para '{tabla_edw}'.",
            detalle="El ETL nunca cargó esta tabla, o el nombre no coincide con tabla_destino.",
        )

    if row["estado"] != "SUCCESS":
        return CheckResult(
            check_name="completion_check",
            severity=Severity.CRITICAL,
            descripcion=(
                f"Última corrida de '{tabla_edw}' terminó en estado '{row['estado']}' "
                f"({row['ultimo_etl_ok']})."
            ),
            detalle=(row["mensaje_error"] or "")[:300],
        )

    return CheckResult(
        check_name="completion_check",
        severity=Severity.OK,
        descripcion=(
            f"Última corrida de '{tabla_edw}' fue SUCCESS el {row['ultimo_etl_ok']} "
            f"({row['registros_carg']} filas cargadas)."
        ),
        valor_edw=row["registros_carg"],
    )
