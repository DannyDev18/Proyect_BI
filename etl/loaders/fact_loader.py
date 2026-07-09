# etl/loaders/fact_loader.py
import pandas as pd
import logging
from connectors.postgres_connector import PostgresConnector
from sqlalchemy import text

logger = logging.getLogger("ETLLoader.Fact")

def load_facts_full(pg: PostgresConnector, df: pd.DataFrame, tabla: str, conn=None) -> int:
    """
    Carga de tablas de hechos (Truncate & Load).
    Útil para snapshots diarios completos (como Inventario).
    """
    logger.info(f"Aplicando Truncate/Reload sobre tabla de hechos: {tabla}")
    return pg.load_dataframe(df, tabla=tabla, modo='truncate', conn=conn)

def load_facts_incremental(pg: PostgresConnector, df: pd.DataFrame, tabla: str, date_col: str,
                           dt_start: str, dt_end: str, conn=None) -> int:
    """
    Carga incremental de tablas de hechos basada en fecha.
    Para evitar duplicados si se re-ejecuta, elimina primero el bloque de la partición lógica
    (fecha_inicio a fecha_fin) en el EDW, para luego insertar los nuevos.

    Auditoría 09 (H4): si se pasa `conn`, el DELETE y el INSERT posterior comparten la misma
    transacción (atómico); si no, cada uno abre/comitea la suya (comportamiento previo).
    """
    if df.empty:
        return 0

    schema = pg.config.PG_SCHEMA
    engine = pg.connect()

    sql_delete = text(f"""
        DELETE FROM {schema}.{tabla}
        WHERE {date_col} >= :dt_start AND {date_col} <= :dt_end
    """)

    if conn is not None:
        res = conn.execute(sql_delete, {"dt_start": dt_start, "dt_end": dt_end})
        borrados = res.rowcount
        logger.info(f"Borrados {borrados} registros en {tabla} previos (Idempotencia Rango: {dt_start} - {dt_end}).")
    else:
        with engine.begin() as conn_propia:
            res = conn_propia.execute(sql_delete, {"dt_start": dt_start, "dt_end": dt_end})
            borrados = res.rowcount
            logger.info(f"Borrados {borrados} registros en {tabla} previos (Idempotencia Rango: {dt_start} - {dt_end}).")

    registros = pg.load_dataframe(df, tabla=tabla, modo='append', conn=conn)
    logger.info(f"Cargados {registros} registros nuevos en {tabla}.")
    return registros

def load_facts_append_only(pg: PostgresConnector, df: pd.DataFrame, tabla: str, conn=None) -> int:
    """
    Carga puros INSERTS (Bulk). Asume que los datos origen ya filtran novedades.

    Auditoría 09 (H4): acepta `conn` para participar en la transacción atómica
    DELETE+recarga que arma el orchestrator por tabla.
    """
    logger.info(f"Bulk Insert sobre tabla transaccional: {tabla}")
    return pg.load_dataframe(df, tabla=tabla, modo='append', conn=conn)
