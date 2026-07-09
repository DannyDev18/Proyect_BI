# validator/runner.py
"""Entrypoint del módulo de validación Producción vs EDW. Standalone: no importa nada de
etl/orchestrator.py, etl/transformers/ ni etl/loaders/. Solo reutiliza etl/connectors/ y
etl/config/settings.py, en modo estrictamente SELECT-only en ambos lados.

Uso:
    python -m validator.runner
    python -m validator.runner --entidad ventas
    python -m validator.runner --entidad ventas movimientos_inventario --desde 2026-01-01
    python -m validator.runner --out docs/auditoria/07_validacion_produccion_vs_edw.md

Código de salida:
    0  -> sin hallazgos CRITICAL (puede haber WARNING)
    1  -> al menos un hallazgo CRITICAL o una entidad no evaluada por ETL incompleto
"""
import argparse
import logging
import os
import sys

# Permite ejecutar tanto como 'python -m validator.runner' desde etl/, como
# 'python -m etl.validator.runner' desde la raíz del repo.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import ETLConfig
from connectors.sqlany_connector import SQLAnywhereConnector
from connectors.postgres_connector import PostgresConnector

from validator.config.validation_rules import ENTITIES
from validator.reconciliation.entity_reconciler import reconcile_entity
from validator.models.result_types import Severity
from validator.report.report_builder import build_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("Validator")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validador independiente Producción (SAP) vs EDW. Solo SELECT, no modifica datos."
    )
    parser.add_argument("--entidad", nargs="+", default=None,
                        help="Nombres de entidades a validar (ver validator/config/validation_rules.py). Por defecto, todas.")
    parser.add_argument("--desde", default=None,
                        help="Piso de fecha (YYYY-MM-DD) para el recorte de comparación. Por defecto, ETLConfig.FECHA_HISTORICA.")
    parser.add_argument("--out", default=None,
                        help="Ruta de salida del reporte Markdown. Por defecto, se imprime a stdout.")
    parser.add_argument("--numero-reporte", type=int, default=99,
                        help="Número de auditoría para el encabezado del reporte (docs/auditoria/NN_...).")
    args = parser.parse_args()

    config = ETLConfig()
    fecha_desde = args.desde or config.FECHA_HISTORICA

    entidades = ENTITIES
    if args.entidad:
        entidades = [e for e in ENTITIES if e.nombre in args.entidad]
        no_encontradas = set(args.entidad) - {e.nombre for e in entidades}
        if no_encontradas:
            logger.warning(f"Entidades no registradas, se ignoran: {no_encontradas}")
    if not entidades:
        logger.error("No hay entidades a validar. Revisa --entidad o validation_rules.py.")
        return 1

    sa = SQLAnywhereConnector(config)
    pg = PostgresConnector(config)
    resultados = []
    try:
        sa_engine = sa.connect()
        pg_engine = pg.connect()
        for rule in entidades:
            logger.info(f"Reconciliando entidad '{rule.nombre}' (tabla EDW: {rule.tabla_edw})...")
            resultado = reconcile_entity(rule, sa_engine, pg_engine, config, fecha_desde)
            resultados.append(resultado)
            logger.info(f"[{rule.nombre}] severidad máxima: {resultado.severidad_maxima().value}")
    finally:
        sa.disconnect()
        pg.disconnect()

    reporte = build_report(resultados, fecha_desde, args.numero_reporte)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(reporte)
        logger.info(f"Reporte escrito en {args.out}")
    else:
        print(reporte)

    hay_critico = any(
        (not r.evaluado) or r.severidad_maxima() == Severity.CRITICAL for r in resultados
    )
    return 1 if hay_critico else 0


if __name__ == "__main__":
    sys.exit(main())
