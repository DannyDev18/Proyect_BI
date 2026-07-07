# etl/loaders/dim_loader.py
import pandas as pd
import logging
from sqlalchemy import text
from connectors.postgres_connector import PostgresConnector

logger = logging.getLogger("ETLLoader.Dim")

def load_dim_scd2(pg: PostgresConnector, df_new: pd.DataFrame, tabla: str, claves_negocio: list, desc_col: str) -> int:
    """
    Carga de datos usando Slowly Changing Dimensions Tipo 2.
    - Expiramos los registros existentes mediante claves_negocio si cambia el desc_col.
    - Insertamos los nuevos vigentes.
    """
    if df_new.empty:
        return 0

    schema = pg.config.PG_SCHEMA
    engine = pg.connect()
    
    # 1. Leer vigentes actuales de BD (es_vigente = true)
    claves_str = ", ".join(claves_negocio)
    sql_current = f"""
        SELECT {claves_str}, {desc_col} AS val_actual
        FROM {schema}.{tabla} 
        WHERE es_vigente = TRUE
    """
    try:
        df_current = pd.read_sql(sql_current, engine)
    except Exception as e:
        logger.warning(f"No se pudo leer tabla {tabla} (probablemente nueva). Error: {e}")
        df_current = pd.DataFrame(columns=claves_negocio + ['val_actual'])
    
    # 2. Identificar cambios
    if not df_current.empty:
        df_merged = df_new.merge(df_current, on=claves_negocio, how='left')
        
        # Filtramos aquellos que ya existen y su descripción (o precio) cambió
        mask_cambio =(df_merged['val_actual'].notna()) & (df_merged[desc_col] != df_merged['val_actual'])
        df_cambiados = df_merged[mask_cambio].copy()
        
        # 3. Expirar los antiguos en BD
        if not df_cambiados.empty:
            registros_vencidos = 0
            with engine.begin() as conn:
                for _, row in df_cambiados.iterrows():
                    condiciones = " AND ".join([f"{k} = :{k}" for k in claves_negocio])
                    params = {k: row[k] for k in claves_negocio}
                    sql_expire = text(f"""
                        UPDATE {schema}.{tabla} 
                        SET es_vigente = FALSE, fecha_fin_vigencia = CURRENT_DATE 
                        WHERE es_vigente = TRUE AND {condiciones}
                    """)
                    conn.execute(sql_expire, params)
                    registros_vencidos += 1
            logger.info(f"SCD2 {tabla}: Expirados {registros_vencidos} registros antiguos.")
            
        # 4. Aislar registros que requieren inserción (nuevos o cambiados)
        # Ignoramos si existe y no hay cambio
        mask_sin_cambio = (df_merged['val_actual'].notna()) & (df_merged[desc_col] == df_merged['val_actual'])
        df_new_insert = df_merged[~mask_sin_cambio].drop(columns=['val_actual'])
    else:
        df_new_insert = df_new.copy()

    # 5. Insertar los finalmente válidos
    registros_insertados = 0
    if not df_new_insert.empty:
        # SCD2 records require es_vigente y dates setup
        if 'es_vigente' not in df_new_insert.columns:
            df_new_insert['es_vigente'] = True
        
        registros_insertados = pg.load_dataframe(
             df_new_insert, 
             tabla=tabla, 
             modo='append' # Se insertan nuevos SK (Serial)
        )
        logger.info(f"SCD2 {tabla}: Insertados {registros_insertados} nuevos/actualizados.")
        
    return registros_insertados

def load_dimension(pg: PostgresConnector, df: pd.DataFrame, tabla: str, claves_negocio: list) -> int:
    """Carga estándar UPSERT para dimensiones sin historial completo."""
    logger.info(f"Procesando tabla dimensional: {tabla}")
    return pg.load_dataframe(df, tabla=tabla, modo='upsert', claves_negocio=claves_negocio)

