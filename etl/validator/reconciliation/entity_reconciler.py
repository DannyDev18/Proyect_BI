# reconciliation/entity_reconciler.py
"""Ejecuta, por entidad, el gate de completitud y (si pasa) los checks de reconciliación de
datos entre Producción y el EDW. Es el único módulo que ejecuta SQL: usa exclusivamente los
conectores existentes de etl/connectors/ en modo SELECT-only.
"""
import logging
import os

from validator.config.validation_rules import EntityRule
from validator.checks.completion_check import run_completion_check
from validator.checks.row_count_check import RowCountCheck
from validator.checks.sum_check import SumCheck
from validator.checks.date_range_check import DateRangeCheck
from validator.checks.duplicate_check import DuplicateCheck
from validator.checks.key_diff_check import KeyDiffCheck
from validator.models.result_types import CheckResult, ReconciliationResult, Severity

logger = logging.getLogger(__name__)

QUERIES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "queries")

# Columnas de sumatoria a reconciliar por entidad. Deben existir con ese alias en las dos
# queries de agregación (produccion/edw) de la entidad.
COLUMNAS_SUMA_POR_ENTIDAD = {
    "ventas": ["total_cantidad", "total_valor"],
    "movimientos_inventario": ["total_cantidad", "total_costo"],
}


def _leer_sql(subcarpeta: str, archivo: str) -> str:
    path = os.path.join(QUERIES_DIR, subcarpeta, archivo)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _render(sql: str, config, fecha_desde: str) -> str:
    return (sql
            .replace("{CODEMP}", config.CODEMP)
            .replace("{ESTADO}", config.ESTADO_VALIDO)
            .replace("{FECHA_DESDE}", fecha_desde))


def reconcile_entity(rule: EntityRule, sa_engine, pg_engine, config, fecha_desde: str) -> ReconciliationResult:
    import pandas as pd

    result = ReconciliationResult(entidad=rule.nombre, tabla_edw=rule.tabla_edw)

    # Nivel 1: ¿el ETL completó esta tabla?
    completion = run_completion_check(pg_engine, rule.tabla_edw, fecha_desde)
    result.checks.append(completion)
    if completion.severity == Severity.CRITICAL:
        result.evaluado = False
        result.motivo_no_evaluado = "ETL no completado para esta tabla: se omite la reconciliación de datos."
        logger.warning(f"[{rule.nombre}] {result.motivo_no_evaluado}")
        return result

    # Nivel 2: reconciliación de datos.
    sql_prod = _render(_leer_sql("produccion", rule.query_prod), config, fecha_desde)
    sql_edw = _render(_leer_sql("edw", rule.query_edw), config, fecha_desde)

    df_prod = pd.read_sql(sql_prod, sa_engine)
    df_edw = pd.read_sql(sql_edw, pg_engine)
    prod_row = df_prod.iloc[0]
    edw_row = df_edw.iloc[0]

    result.checks.append(RowCountCheck().run(prod_row, edw_row))
    for columna in COLUMNAS_SUMA_POR_ENTIDAD.get(rule.nombre, []):
        result.checks.append(SumCheck(columna, tolerancia_pct=rule.tolerancia_pct).run(prod_row, edw_row))
    result.checks.append(DateRangeCheck().run(prod_row, edw_row))

    if rule.query_edw_dup:
        sql_dup = _render(_leer_sql("edw", rule.query_edw_dup), config, fecha_desde)
        dup_row = pd.read_sql(sql_dup, pg_engine).iloc[0]
        result.checks.append(DuplicateCheck().run(dup_row))

    if rule.query_edw_keys:
        sql_keys = _render(_leer_sql("edw", rule.query_edw_keys), config, fecha_desde)
        keys_row = pd.read_sql(sql_keys, pg_engine).iloc[0]
        result.checks.append(KeyDiffCheck().run(keys_row))

    return result
