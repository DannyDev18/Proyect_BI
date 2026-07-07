import logging
import sys
import os
import pandas as pd
import hashlib
import hmac
from datetime import datetime, date

from config.settings import ETLConfig
from connectors.sqlany_connector import SQLAnywhereConnector
from connectors.postgres_connector import PostgresConnector
from transformers.dim_tiempo import generar_dim_tiempo
from transformers.dim_transformer import (
    transformar_clientes, transformar_productos,
    transformar_vendedores, transformar_almacenes,
    transformar_sucursales, transformar_proveedores,
    transformar_empleados, transformar_usuarios,
    transformar_formapago, transformar_geografia
)
from transformers.fact_transformer import (
    transformar_ventas_detalle, transformar_inventario_snapshot,
    transformar_movimientos_inventario, transformar_compras,
    transformar_cobros_cxc, transformar_pagos_cxp,
    transformar_nomina, transformar_movimientos_caja,
    transformar_metas_comerciales, transformar_logs_auditoria,
    transformar_devoluciones
)
from loaders.dim_loader import load_dimension, load_dim_scd2
from loaders.fact_loader import load_facts_append_only
from sqlalchemy import text

# Configurar logs básicos
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("ETLOrchestrator")

def get_last_etl_date(pg: PostgresConnector, tabla: str) -> date:
    """Busca la última fecha en la que se corrió exitosamente una tabla en el EDW."""
    sql = "SELECT MAX(ultimo_etl_ok) FROM edw.etl_control WHERE tabla_destino = :tabla AND estado = 'SUCCESS'"
    engine = pg.connect()
    try:
        with engine.begin() as conn:
            res = conn.execute(text(sql), {"tabla": tabla}).scalar()
            if res:
                return res.date()
    except Exception as e:
        logger.warning(f"No se pudo consultar etl_control (¿primera ejecución?): {e}")
    # Si no existe, retorna una fecha base histórica
    return date(1900, 1, 1)

def registrar_control_etl(pg: PostgresConnector, tabla: str, registros: int, estado: str, msj: str = None, duracion: int = 0):
    sql = """
        INSERT INTO edw.etl_control (tabla_destino, ultimo_etl_ok, registros_carg, estado, duracion_seg, mensaje_error)
        VALUES (:tabla, NOW(), :regs, :estado, :duracion, :msj)
    """
    try:
        engine = pg.connect()
        with engine.begin() as conn:
            conn.execute(text(sql), {
                "tabla": tabla, "regs": registros, "estado": estado,
                "duracion": duracion, "msj": msj
            })
    except Exception as e:
        logger.error(f"Error escribiendo en logs de control: {e}")

PIPELINE_CONFIG = [
    # ---------------- DIMENSIONES ----------------
    {'file': 'geografia_extractor.sql', 'tabla': 'dim_geografia', 'transform': transformar_geografia, 'loader': 'dim', 'keys': ['pais', 'provincia', 'canton', 'parroquia']},
    {'file': 'sucursales_extractor.sql', 'tabla': 'dim_sucursal', 'transform': transformar_sucursales, 'loader': 'dim', 'keys': ['codigo_sucursal']},
    {'file': 'almacenes_extractor.sql', 'tabla': 'dim_almacen', 'transform': transformar_almacenes, 'loader': 'dim', 'keys': ['codemp', 'codalm']},
    {'file': 'clientes_extractor.sql', 'tabla': 'dim_cliente', 'transform': transformar_clientes, 'loader': 'scd2', 'keys': ['hash_anonimo'], 'desc_col': 'clase_cliente', 'delta_col': 'fecult'},
    {'file': 'proveedores_extractor.sql', 'tabla': 'dim_proveedor', 'transform': transformar_proveedores, 'loader': 'dim', 'keys': ['codemp', 'codpro']},
    {'file': 'vendedores_extractor.sql', 'tabla': 'dim_vendedor', 'transform': transformar_vendedores, 'loader': 'dim', 'keys': ['codemp', 'codven'], 'delta_col': 'fecult'},
    {'file': 'empleados_extractor.sql', 'tabla': 'dim_empleado', 'transform': transformar_empleados, 'loader': 'dim', 'keys': ['codemp', 'codemple'], 'delta_col': 'fecha_ing'},
    {'file': 'usuarios_extractor.sql', 'tabla': 'dim_usuario', 'transform': transformar_usuarios, 'loader': 'dim', 'keys': ['codemp', 'codusu']},
    {'file': 'formapago_extractor.sql', 'tabla': 'dim_formapago', 'transform': transformar_formapago, 'loader': 'dim', 'keys': ['codemp', 'codforpag']},
    {'file': 'articulos_extractor.sql', 'tabla': 'dim_producto', 'transform': transformar_productos, 'loader': 'scd2', 'keys': ['codemp', 'codart'], 'desc_col': 'nombre_articulo', 'delta_col': 'fecult'},
    
    # ---------------- HECHOS ----------------
    {'file': 'kardex_extractor.sql', 'tabla': 'fact_movimientos_inventario', 'transform': transformar_movimientos_inventario, 'loader': 'fact_inc', 'delta_col': 'fecdoc', 'pg_date_col': 'fecha_sk'},
    {'file': 'facturas_detalle_extractor.sql', 'tabla': 'fact_ventas_detalle', 'transform': transformar_ventas_detalle, 'loader': 'fact_inc', 'delta_col': 'e.fecfac', 'pg_date_col': 'fecha_sk'},
    {'file': 'compras_detalle_extractor.sql', 'tabla': 'fact_compras', 'transform': transformar_compras, 'loader': 'fact_inc', 'delta_col': 'e.fecfac', 'pg_date_col': 'fecha_sk'},
    {'file': 'cobros_cxc_extractor.sql', 'tabla': 'fact_cobros_cxc', 'transform': transformar_cobros_cxc, 'loader': 'fact_inc', 'delta_col': 'fecemi', 'pg_date_col': 'fecha_sk'},
    {'file': 'pagos_cxp_extractor.sql', 'tabla': 'fact_pagos_cxp', 'transform': transformar_pagos_cxp, 'loader': 'fact_inc', 'delta_col': 'fecemi', 'pg_date_col': 'fecha_sk'},
    {'file': 'nomina_extractor.sql', 'tabla': 'fact_nomina', 'transform': transformar_nomina, 'loader': 'fact_inc', 'delta_col': 'fecdoc', 'pg_date_col': 'fecha_sk'},
    {'file': 'movimientos_caja_extractor.sql', 'tabla': 'fact_movimientos_caja', 'transform': transformar_movimientos_caja, 'loader': 'fact_inc', 'delta_col': 'fecape', 'pg_date_col': 'fecha_sk'},
    {'file': 'metas_comerciales_extractor.sql', 'tabla': 'fact_metas_comerciales', 'transform': transformar_metas_comerciales, 'loader': 'fact_inc', 'delta_col': 'fecmes', 'pg_date_col': 'fecha_sk'},
    {'file': 'devoluciones_detalle_extractor.sql', 'tabla': 'fact_devoluciones', 'transform': transformar_devoluciones, 'loader': 'fact_inc', 'delta_col': 'e.fecfac', 'pg_date_col': 'fecha_sk'}
]

def resolver_llaves_hecho(pg: PostgresConnector, df: pd.DataFrame, tbl_destino: str) -> pd.DataFrame:
    if df.empty:
        return df
    
    engine = pg.connect()
    schema = pg.config.PG_SCHEMA
    df = df.copy()
    
    # 1. Resolver fecha_sk (ej. buscando fecdoc, fecfac, fecemi, fecape, fecmes)
    col_fecha_origen = None
    for f_col in ['fecdoc', 'fecfac', 'fecemi', 'fecape', 'fecmes', 'fecha_ingreso', 'fecha']:
        if f_col in df.columns:
            col_fecha_origen = f_col
            break
            
    if col_fecha_origen:
        df[col_fecha_origen] = pd.to_datetime(df[col_fecha_origen], errors='coerce')
        df_fecha = pd.read_sql(f"SELECT fecha_sk, fecha_completa FROM {schema}.dim_fecha", engine)
        df_fecha['fecha_completa'] = pd.to_datetime(df_fecha['fecha_completa']).dt.date
        df['fecha_lookup'] = df[col_fecha_origen].dt.date
        df = df.merge(df_fecha, left_on='fecha_lookup', right_on='fecha_completa', how='left')
        df.drop(columns=['fecha_lookup', 'fecha_completa'], errors='ignore', inplace=True)
    
    # 2. Resolver producto_sk (codemp, codart)
    if 'codart' in df.columns:
        df_prod = pd.read_sql(f"SELECT producto_sk, codemp, codart FROM {schema}.dim_producto WHERE es_vigente = TRUE", engine)
        df = df.merge(df_prod, on=['codemp', 'codart'], how='left')

    # 3. Resolver cliente_sk (codcli -> hash_anonimo)
    if 'codcli' in df.columns:
        salt = pg.config.PII_SALT
        df['hash_anonimo'] = df['codcli'].apply(
            lambda x: hmac.new(salt.encode(), str(x).encode(), hashlib.sha256).hexdigest()
        )
        df_cli = pd.read_sql(f"SELECT cliente_sk, hash_anonimo FROM {schema}.dim_cliente WHERE es_vigente = TRUE", engine)
        df = df.merge(df_cli, on=['hash_anonimo'], how='left')
        df.drop(columns=['hash_anonimo'], errors='ignore', inplace=True)

    # 4. Resolver proveedor_sk (codemp, codpro)
    if 'codpro' in df.columns:
        df_pro = pd.read_sql(f"SELECT proveedor_sk, codemp, codpro FROM {schema}.dim_proveedor", engine)
        df = df.merge(df_pro, on=['codemp', 'codpro'], how='left')

    # 5. Resolver vendedor_sk (codemp, codven)
    if 'codven' in df.columns:
        df_ven = pd.read_sql(f"SELECT vendedor_sk, codemp, codven FROM {schema}.dim_vendedor", engine)
        df = df.merge(df_ven, on=['codemp', 'codven'], how='left')

    # 6. Resolver empleado_sk (codemp, codemple)
    if 'codemple' in df.columns:
        df_emp = pd.read_sql(f"SELECT empleado_sk, codemp, codemple FROM {schema}.dim_empleado", engine)
        df = df.merge(df_emp, on=['codemp', 'codemple'], how='left')

    # 7. Resolver usuario_sk (codemp, codusu)
    if 'codusu' in df.columns:
        df_usu = pd.read_sql(f"SELECT usuario_sk, codemp, codusu FROM {schema}.dim_usuario", engine)
        df = df.merge(df_usu, on=['codemp', 'codusu'], how='left')

    # 8. Resolver formapago_sk (codemp, codforpag)
    if 'codforpag' in df.columns:
        df_fp = pd.read_sql(f"SELECT formapago_sk, codemp, codforpag FROM {schema}.dim_formapago", engine)
        df = df.merge(df_fp, on=['codemp', 'codforpag'], how='left')

    # 9. Resolver almacen_sk (codemp, codalm)
    if 'codalm' in df.columns:
        df_alm = pd.read_sql(f"SELECT almacen_sk, codemp, codalm, establ FROM {schema}.dim_almacen", engine)
        df = df.merge(df_alm, on=['codemp', 'codalm'], how='left', suffixes=('', '_alm'))
        if 'establ' not in df.columns and 'establ_alm' in df.columns:
            df['establ'] = df['establ_alm']
            df.drop(columns=['establ_alm'], errors='ignore', inplace=True)

    # 10. Resolver sucursal_sk (codemp, establ)
    if 'establ' in df.columns:
        df_suc = pd.read_sql(f"SELECT sucursal_sk, codemp, establ FROM {schema}.dim_sucursal", engine)
        df = df.merge(df_suc, on=['codemp', 'establ'], how='left')
    else:
        df_suc = pd.read_sql(f"SELECT sucursal_sk FROM {schema}.dim_sucursal LIMIT 1", engine)
        if not df_suc.empty:
            df['sucursal_sk'] = df_suc['sucursal_sk'].iloc[0]

    # Prevenir que haya nulos en SKs obligatorios
    for sk_col in ['fecha_sk', 'producto_sk', 'cliente_sk', 'sucursal_sk', 'vendedor_sk', 'formapago_sk', 'proveedor_sk', 'almacen_sk', 'empleado_sk', 'usuario_sk']:
        if sk_col in df.columns:
            if df[sk_col].isnull().any():
                try:
                    p_engine = pg.connect()
                    p_tbl = 'dim_fecha' if sk_col == 'fecha_sk' else sk_col.replace('_sk', '')
                    if p_tbl == 'formapago': p_tbl = 'dim_formapago'
                    elif p_tbl == 'fecha': p_tbl = 'dim_fecha'
                    elif p_tbl == 'vendedor': p_tbl = 'dim_vendedor'
                    elif p_tbl == 'proveedor': p_tbl = 'dim_proveedor'
                    elif p_tbl == 'empleado': p_tbl = 'dim_empleado'
                    elif p_tbl == 'usuario': p_tbl = 'dim_usuario'
                    elif p_tbl == 'producto': p_tbl = 'dim_producto'
                    elif p_tbl == 'almacen': p_tbl = 'dim_almacen'
                    elif p_tbl == 'sucursal': p_tbl = 'dim_sucursal'
                    elif p_tbl == 'cliente': p_tbl = 'dim_cliente'
                    
                    sk_default = pd.read_sql(f"SELECT {sk_col} FROM {schema}.{p_tbl} WHERE {sk_col} = -1", p_engine)
                    if sk_default.empty:
                        sk_default = pd.read_sql(f"SELECT {sk_col} FROM {schema}.{p_tbl} LIMIT 1", p_engine)
                    
                    if not sk_default.empty:
                        df[sk_col] = df[sk_col].fillna(int(sk_default[sk_col].iloc[0]))
                except Exception as ex_def:
                    logger.warning(f"No se pudo resolver default para {sk_col}: {ex_def}")

    # Asegurar tipo de dato entero
    for col in df.columns:
        if col.endswith('_sk'):
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)

    return df

def load_data_chunk(pg: PostgresConnector, df_transformed: pd.DataFrame, config_item: dict) -> int:
    l_type = config_item['loader']
    if l_type == 'dim':
        return load_dimension(pg, df_transformed, config_item['tabla'], config_item['keys'])
    elif l_type == 'scd2':
        return load_dim_scd2(pg, df_transformed, config_item['tabla'], config_item['keys'], config_item.get('desc_col'))
    else:
        return load_facts_append_only(pg, df_transformed, config_item['tabla'])

def run_etl(config: ETLConfig) -> None:
    inicio = datetime.now()
    logger.info(f"=== INICIO DEL PIPELINE ETL PROD - {inicio} ===")
    
    pg = PostgresConnector(config)
    sa = SQLAnywhereConnector(config)
    schema = config.PG_SCHEMA
    extractors_path = os.path.join(os.path.dirname(__file__), 'extractors')
    
    try:
        sa.connect()
        pg.connect()

        # 1. Dimensión Tiempo
        logger.info("Generando Dimensión Fecha...")
        df_fecha = generar_dim_tiempo()
        pg.load_dataframe(df_fecha, 'dim_fecha', 'upsert', claves_negocio=['fecha_completa'])
        logger.info("Dimensión Tiempo actualizada exitosamente.")

        # 2. Extractores Modulares
        for cfg in PIPELINE_CONFIG:
            sql_file = os.path.join(extractors_path, cfg['file'])
            if not os.path.isfile(sql_file):
                logger.warning(f"Archivo extractor SQL '{cfg['file']}' no encontrado, saltando...")
                continue
            
            with open(sql_file, 'r', encoding='utf-8') as f:
                sql_query = f.read()

            last_date = get_last_etl_date(pg, cfg['tabla'])
            last_date_str = last_date.strftime('%Y-%m-%d')
            
            logger.info(f"Iniciando extracción para: {cfg['tabla']} desde la fecha >= {last_date_str}")
            
            # Idempotencia: Si es FactIncremental y no es re-carga inicial desde cero
            if cfg.get('loader') == 'fact_inc' and last_date.year > 1900:
                pg_date_col = cfg.get('pg_date_col', 'fecha_sk')
                
                # Postgres fecha_sk es YYMMDD int formated, transformamos last_date_str a ese formato numérico?
                # Cierto! En nuestro DW dim_tiempo, 'fecha_sk' es un int ej. 20260703 o DATE? 
                # Si es Integer, lo comparamos pasando la fecha sin guiones.
                # ASUMIMOS que fecha_sk puede recibir un '2026-07-03' o es un DATE nativo si está bien diseñado.
                # Para evitar problemas:
                date_int = int(last_date.strftime('%Y%m%d'))
                delete_sql = f"DELETE FROM {schema}.{cfg['tabla']} WHERE {pg_date_col} >= :d_int"
                
                with pg.connect().begin() as conn:
                    res = conn.execute(text(delete_sql), {"d_int": date_int})
                    logger.info(f"Idempotencia: {res.rowcount} registros eliminados en {cfg['tabla']} a partir de {date_int}")

            # Append Incremental SAP Query Where
            if cfg.get('delta_col'):
                # Inyectamos el AND asumiendo que el sql termina en ';'
                sql_query = sql_query.replace(';', f" AND {cfg['delta_col']} >= '{last_date_str}';")

            total_loaded = 0
            chunk_idx = 1
            start_t_table = datetime.now()
            
            for df_chunk in sa.yield_query_chunks(sql_query, chunksize=10000):
                logger.info(f"Procesando Chunk #{chunk_idx} ({len(df_chunk)} registros)...")
                if cfg.get('transform'):
                    df_chunk = cfg['transform'](df_chunk)
                
                # --- INTERCEPCIÓN PII: Dimensión Cliente ---
                if cfg['tabla'] == 'dim_cliente':
                    salt = config.PII_SALT
                    df_chunk['hash_anonimo'] = df_chunk['codcli'].apply(
                        lambda x: hmac.new(salt.encode(), str(x).encode(), hashlib.sha256).hexdigest()
                    )
                    
                    df_lookup = df_chunk[['hash_anonimo', 'codcli', 'nombre_cliente']].copy()
                    df_lookup.rename(columns={'codcli': 'id_cliente_transaccional'}, inplace=True)
                    df_lookup.drop_duplicates(subset=['hash_anonimo'], inplace=True)
                    
                    original_schema = pg.config.PG_SCHEMA
                    pg.config.PG_SCHEMA = 'public'
                    
                    pg.load_dataframe(df_lookup, tabla='cliente_lookup', modo='upsert', claves_negocio=['hash_anonimo'])
                    pg.config.PG_SCHEMA = original_schema
                    
                    df_chunk.drop(columns=['ruc_cedula', 'nombre_cliente', 'codcli'], errors='ignore', inplace=True)
                # ---------------------------------------------
                
                if cfg.get('loader') not in ['dim', 'scd2']:
                    df_chunk = resolver_llaves_hecho(pg, df_chunk, cfg['tabla'])
                
                loaded_records = load_data_chunk(pg, df_chunk, cfg)
                total_loaded += loaded_records
                chunk_idx += 1
            
            dur_table = int((datetime.now() - start_t_table).total_seconds())
            registrar_control_etl(pg, cfg['tabla'], total_loaded, 'SUCCESS', 'Carga Completada en Chunks', dur_table)
            logger.info(f"✅ FINALIZADO {cfg['tabla']}: {total_loaded} registros en {dur_table} segs.")

    except Exception as e:
        logger.critical(f"Falla crítica: {e}", exc_info=True)
        registrar_control_etl(pg, 'PIPELINE_GENERAL', 0, 'FAIL', str(e), 0)
        raise
    finally:
        sa.disconnect()
        pg.disconnect()
        duracion = int((datetime.now() - inicio).total_seconds())
        logger.info(f"=== FIN PIPELINE ETL - Duración: {duracion} segs ===")

if __name__ == "__main__":
    logger.info("Cargando variables...")
    config = ETLConfig()
    run_etl(config)