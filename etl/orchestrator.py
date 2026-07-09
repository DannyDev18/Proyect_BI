import argparse
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
    transformar_formapago
)
from transformers.fact_transformer import (
    transformar_ventas_detalle, transformar_inventario_snapshot,
    transformar_movimientos_inventario, transformar_compras,
    transformar_cobros_cxc, transformar_pagos_cxp,
    transformar_nomina, transformar_movimientos_caja,
    transformar_metas_comerciales, transformar_logs_auditoria,
    transformar_devoluciones, transformar_transferencias
)
from loaders.dim_loader import load_dimension, load_dim_scd2
from loaders.fact_loader import load_facts_append_only
from sqlalchemy import text, inspect

# Configurar logs básicos
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("ETLOrchestrator")

# Auditoría 09 (H6): contador de fallas reales de control (distintas de "la tabla de control
# todavía no existe"), para reportarlo en el resumen final en vez de que solo quede en logs.
_STATS_CONTROL: dict = {'fallas': 0}

def get_last_etl_date(pg: PostgresConnector, tabla: str) -> date:
    """Busca la última fecha en la que se corrió exitosamente una tabla en el EDW."""
    engine = pg.connect()
    if not inspect(engine).has_table('etl_control', schema='edw'):
        # Primera ejecución real: la tabla de control todavía no existe.
        return date(1900, 1, 1)
    sql = "SELECT MAX(ultimo_etl_ok) FROM edw.etl_control WHERE tabla_destino = :tabla AND estado = 'SUCCESS'"
    try:
        with engine.begin() as conn:
            res = conn.execute(text(sql), {"tabla": tabla}).scalar()
            if res:
                return res.date()
    except Exception as e:
        # La tabla existe pero la consulta falló (permisos/conectividad/schema): esto NO es
        # "primera ejecución", es un error real que puede esconder un problema de infraestructura.
        # Se cuenta aparte (H6) para que el resumen final del pipeline lo muestre, no solo el log.
        _STATS_CONTROL['fallas'] += 1
        logger.error(f"Error consultando etl_control para '{tabla}': {e}", exc_info=True)
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
        _STATS_CONTROL['fallas'] += 1
        logger.error(f"Error escribiendo en logs de control para '{tabla}': {e}", exc_info=True)

def validar_configuracion(config: ETLConfig) -> None:
    """Valida precondiciones de seguridad antes de correr el pipeline.
    El salt PII no puede quedar en su valor por defecto/inseguro (privacidad de datos)."""
    if not config.PII_SALT or config.PII_SALT == config._PII_SALT_INSEGURO:
        raise ValueError(
            "PII_SALT no está configurado o usa el valor por defecto inseguro. "
            "Defina una variable de entorno PII_SALT robusta y única antes de ejecutar el ETL "
            "(el hashing de clientes depende de este salt; un valor conocido permite re-identificación)."
        )


def render_sql(sql: str, config: ETLConfig, fecha_desde: str) -> str:
    """Sustituye los tokens de los extractores por valores de configuración.
    Tokens soportados:
      {CODEMP}       -> empresa (config.CODEMP)
      {ESTADO}       -> estado de documento válido (config.ESTADO_VALIDO)
      {FECHA_DESDE}  -> piso de fecha para la extracción (incremental o histórico)
    Es robusto ante UNION ALL: cada rama trae su propio token en su WHERE."""
    return (sql
            .replace('{CODEMP}', config.CODEMP)
            .replace('{ESTADO}', config.ESTADO_VALIDO)
            .replace('{FECHA_DESDE}', fecha_desde))


# El lookup cliente_sk<->identidad real (PII) vive fuera del schema `edw` a propósito: el resto
# del EDW es de solo-lectura anonimizada (hash_anonimo), y este lookup es la única tabla con PII
# real, aislada en `public` para poder aplicarle permisos/retención distintos al resto del DW.
SCHEMA_PUBLICO_LOOKUP = 'public'

# Caché de dimensiones por corrida: evita releer dim_* completas en cada chunk (rendimiento).
_DIM_CACHE: dict = {}

def _leer_dim_cacheada(engine, key: str, sql: str) -> pd.DataFrame:
    if key not in _DIM_CACHE:
        _DIM_CACHE[key] = pd.read_sql(sql, engine)
    return _DIM_CACHE[key].copy()


def asegurar_registros_desconocidos(pg: PostgresConnector) -> None:
    """Crea los registros centinela -1 usados cuando una clave no puede resolverse."""
    schema = pg.config.PG_SCHEMA
    inserts = [
        f"""
        INSERT INTO {schema}.dim_fecha (
            fecha_sk, fecha_completa, anio, trimestre, mes, nombre_mes,
            semana_anio, dia_mes, dia_semana, nombre_dia, es_fin_semana,
            es_feriado, semestre, periodo_fiscal
        )
        SELECT -1, DATE '1900-01-01', 1900, 1, 1, 'Desconocido',
               1, 1, 1, 'Desconocido', FALSE, FALSE, 1, 'UNK'
        WHERE NOT EXISTS (SELECT 1 FROM {schema}.dim_fecha WHERE fecha_sk = -1)
        """,
        f"""
        INSERT INTO {schema}.dim_sucursal (
            sucursal_sk, codemp, establ, codigo_sucursal, nombre_sucursal,
            direccion, telefono, activa
        )
        SELECT -1, '00', '000', 'UNK', 'Desconocida', NULL, NULL, TRUE
        WHERE NOT EXISTS (SELECT 1 FROM {schema}.dim_sucursal WHERE sucursal_sk = -1)
        """,
        f"""
        INSERT INTO {schema}.dim_almacen (
            almacen_sk, codemp, codalm, nombre_almacen, establ
        )
        SELECT -1, '00', 'UNK', 'Desconocido', '000'
        WHERE NOT EXISTS (SELECT 1 FROM {schema}.dim_almacen WHERE almacen_sk = -1)
        """,
        f"""
        INSERT INTO {schema}.dim_producto (
            producto_sk, codemp, codart, nombre_articulo, clase, nombre_clase,
            subclase, nombre_subclase, unidad, nombre_unidad, precio_oficial,
            costo_promedio, estado, es_servicio, fecha_inicio_vigencia,
            fecha_fin_vigencia, es_vigente
        )
        SELECT -1, '00', 'UNK', 'Desconocido', 'UNK', 'Desconocido',
               'UNK', 'Desconocido', 'UND', 'Desconocido', 0, 0,
               'U', FALSE, CURRENT_DATE, NULL, TRUE
        WHERE NOT EXISTS (SELECT 1 FROM {schema}.dim_producto WHERE producto_sk = -1)
        """,
        f"""
        INSERT INTO {schema}.dim_cliente (
            cliente_sk, hash_anonimo, codemp, tipo_id, clase_cliente,
            nombre_clase, zona, nombre_zona, ciudad, limite_credito,
            dias_credito, estado, sexo, fecha_inicio_vigencia,
            fecha_fin_vigencia, es_vigente
        )
        SELECT -1, 'UNK', '00', NULL, NULL, NULL, NULL, NULL, NULL, 0,
               0, 'U', 'U', CURRENT_DATE, NULL, TRUE
        WHERE NOT EXISTS (SELECT 1 FROM {schema}.dim_cliente WHERE cliente_sk = -1)
        """,
        f"""
        INSERT INTO {schema}.dim_proveedor (
            proveedor_sk, codemp, codpro, nombre_proveedor, ruc, ciudad,
            dias_credito, estado
        )
        SELECT -1, '00', 'UNK', 'Desconocido', NULL, NULL, 0, 'U'
        WHERE NOT EXISTS (SELECT 1 FROM {schema}.dim_proveedor WHERE proveedor_sk = -1)
        """,
        f"""
        INSERT INTO {schema}.dim_vendedor (
            vendedor_sk, codemp, codven, nombre_vendedor, comision, activo
        )
        SELECT -1, '00', 'UNK', 'Desconocido', 0, TRUE
        WHERE NOT EXISTS (SELECT 1 FROM {schema}.dim_vendedor WHERE vendedor_sk = -1)
        """,
        f"""
        INSERT INTO {schema}.dim_empleado (
            empleado_sk, codemp, codemple, nombre_empleado, cedula, cargo,
            departamento, sueldo_base, fecha_ingreso, activo
        )
        SELECT -1, '00', 'UNK', 'Desconocido', 'UNK', NULL, NULL, 0, NULL, TRUE
        WHERE NOT EXISTS (SELECT 1 FROM {schema}.dim_empleado WHERE empleado_sk = -1)
        """,
        f"""
        INSERT INTO {schema}.dim_usuario (
            usuario_sk, codemp, codusu, nombre_usuario, rol, estado
        )
        SELECT -1, '00', 'UNK', 'Desconocido', NULL, 'A'
        WHERE NOT EXISTS (SELECT 1 FROM {schema}.dim_usuario WHERE usuario_sk = -1)
        """,
        f"""
        INSERT INTO {schema}.dim_formapago (
            formapago_sk, codemp, codforpag, nombre_forma_pago, dias_plazo
        )
        SELECT -1, '00', 'UNK', 'Desconocido', 0
        WHERE NOT EXISTS (SELECT 1 FROM {schema}.dim_formapago WHERE formapago_sk = -1)
        """,
        # Auditoría 09 (H2): el INSERT a dim_geografia fue removido — esa tabla no existe en el
        # EDW desde la auditoría 07 (H4); al estar todos estos INSERT en una sola transacción,
        # ese INSERT fallido hacía rollback de TODOS los centinelas válidos y abortaba el
        # pipeline completo en cada corrida.
    ]

    engine = pg.connect()
    with engine.begin() as conn:
        for sql in inserts:
            conn.execute(text(sql))


# Auditoría 09 (H7): mapeo único columna_sk -> tabla dimensión, reutilizado tanto por
# resolver_llaves_hecho (relleno de defaults) como por el chequeo de dependencias (H3/H5),
# en vez de duplicarlo en una cadena de elif.
DIM_TABLE_BY_SK = {
    'fecha_sk': 'dim_fecha',
    'producto_sk': 'dim_producto',
    'cliente_sk': 'dim_cliente',
    'sucursal_sk': 'dim_sucursal',
    'vendedor_sk': 'dim_vendedor',
    'formapago_sk': 'dim_formapago',
    'proveedor_sk': 'dim_proveedor',
    'almacen_sk': 'dim_almacen',
    'empleado_sk': 'dim_empleado',
    'usuario_sk': 'dim_usuario',
    'estado_documento_sk': 'dim_estado_documento',
    'almacen_origen_sk': 'dim_almacen',
    'almacen_destino_sk': 'dim_almacen',
}

# Auditoría 09 (H3): columnas de llave de negocio -> dimensión que resuelven, usado para
# inferir de qué dimensiones depende cada hecho sin mantener una lista aparte a mano.
DIM_TABLE_BY_BUSINESS_KEY = {
    'codart': 'dim_producto',
    'codcli': 'dim_cliente',
    'codpro': 'dim_proveedor',
    'codven': 'dim_vendedor',
    'codemple': 'dim_empleado',
    'codusu': 'dim_usuario',
    'codforpag': 'dim_formapago',
    'codalm': 'dim_almacen',
    'establ': 'dim_sucursal',
}

PIPELINE_CONFIG = [
    # ---------------- DIMENSIONES ----------------
    # geografia_extractor.sql sin tabla destino: Dim_Geografia fue retirada del EDW (auditoría
    # 07, H4) y transformar_geografia era código huérfano (auditoría 08, F11).
    {'file': 'sucursales_extractor.sql', 'tabla': 'dim_sucursal', 'transform': transformar_sucursales, 'loader': 'dim', 'keys': ['codemp', 'codigo_sucursal']},
    {'file': 'almacenes_extractor.sql', 'tabla': 'dim_almacen', 'transform': transformar_almacenes, 'loader': 'dim', 'keys': ['codemp', 'codalm']},
    {'file': 'clientes_extractor.sql', 'tabla': 'dim_cliente', 'transform': transformar_clientes, 'loader': 'scd2', 'keys': ['hash_anonimo'], 'desc_col': 'clase_cliente', 'delta_col': 'fecult'},
    {'file': 'proveedores_extractor.sql', 'tabla': 'dim_proveedor', 'transform': transformar_proveedores, 'loader': 'dim', 'keys': ['codemp', 'codpro']},
    {'file': 'vendedores_extractor.sql', 'tabla': 'dim_vendedor', 'transform': transformar_vendedores, 'loader': 'dim', 'keys': ['codemp', 'codven'], 'delta_col': 'fecult'},
    {'file': 'empleados_extractor.sql', 'tabla': 'dim_empleado', 'transform': transformar_empleados, 'loader': 'dim', 'keys': ['codemp', 'codemple'], 'delta_col': 'fecha_ing'},
    {'file': 'usuarios_extractor.sql', 'tabla': 'dim_usuario', 'transform': transformar_usuarios, 'loader': 'dim', 'keys': ['codemp', 'codusu']},
    {'file': 'formapago_extractor.sql', 'tabla': 'dim_formapago', 'transform': transformar_formapago, 'loader': 'dim', 'keys': ['codemp', 'codforpag']},
    {'file': 'articulos_extractor.sql', 'tabla': 'dim_producto', 'transform': transformar_productos, 'loader': 'scd2', 'keys': ['codemp', 'codart'], 'desc_col': 'nombre_articulo', 'delta_col': 'fecult'},

    # ---------------- HECHOS ----------------
    # Auditoría 09 (H12): el orden ENTRE hechos es irrelevante — ningún hecho referencia a
    # otro hecho (solo a dimensiones), así que no hay FK hecho->hecho que imponga precedencia.
    # 'depende_de' (auditoría 09, H3/H5): dimensiones de las que este hecho resuelve llaves,
    # inferido de las columnas de negocio que expone su extractor (ver auditoría 09 evidencia
    # por extractor). Se usa para (a) validar el orden dimensiones-antes-que-hechos al inicio
    # de run_etl (H5) y (b) saltar el hecho si alguna de sus dimensiones falló en esta misma
    # corrida (H3), en vez de procesarlo igual contra una dimensión incompleta.
    # Snapshot diario de existencias (foto de stock por bodega). Reemplaza sólo la foto de hoy.
    {'file': 'existencias_extractor.sql', 'tabla': 'fact_inventario_snapshot', 'transform': transformar_inventario_snapshot, 'loader': 'fact_inc', 'pg_date_col': 'fecha_sk', 'snapshot': True, 'depende_de': ['dim_producto', 'dim_almacen', 'dim_sucursal']},
    {'file': 'kardex_extractor.sql', 'tabla': 'fact_movimientos_inventario', 'transform': transformar_movimientos_inventario, 'loader': 'fact_inc', 'delta_col': 'fecdoc', 'pg_date_col': 'fecha_sk', 'depende_de': ['dim_producto', 'dim_almacen', 'dim_sucursal', 'dim_cliente', 'dim_vendedor']},
    {'file': 'facturas_detalle_extractor.sql', 'tabla': 'fact_ventas_detalle', 'transform': transformar_ventas_detalle, 'loader': 'fact_inc', 'delta_col': 'e.fecfac', 'pg_date_col': 'fecha_sk', 'depende_de': ['dim_producto', 'dim_cliente', 'dim_vendedor', 'dim_almacen', 'dim_sucursal']},
    {'file': 'compras_detalle_extractor.sql', 'tabla': 'fact_compras', 'transform': transformar_compras, 'loader': 'fact_inc', 'delta_col': 'e.fecfac', 'pg_date_col': 'fecha_sk', 'depende_de': ['dim_producto', 'dim_proveedor', 'dim_almacen', 'dim_sucursal']},
    {'file': 'cobros_cxc_extractor.sql', 'tabla': 'fact_cobros_cxc', 'transform': transformar_cobros_cxc, 'loader': 'fact_inc', 'delta_col': 'fecemi', 'pg_date_col': 'fecha_sk', 'depende_de': ['dim_cliente', 'dim_vendedor', 'dim_formapago']},
    {'file': 'pagos_cxp_extractor.sql', 'tabla': 'fact_pagos_cxp', 'transform': transformar_pagos_cxp, 'loader': 'fact_inc', 'delta_col': 'fecemi', 'pg_date_col': 'fecha_sk', 'depende_de': ['dim_proveedor', 'dim_formapago']},
    {'file': 'nomina_extractor.sql', 'tabla': 'fact_nomina', 'transform': transformar_nomina, 'loader': 'fact_inc', 'delta_col': 'fecdoc', 'pg_date_col': 'fecha_sk', 'depende_de': ['dim_empleado']},
    {'file': 'movimientos_caja_extractor.sql', 'tabla': 'fact_movimientos_caja', 'transform': transformar_movimientos_caja, 'loader': 'fact_inc', 'delta_col': 'fecape', 'pg_date_col': 'fecha_sk', 'depende_de': ['dim_usuario', 'dim_formapago']},
    {'file': 'metas_comerciales_extractor.sql', 'tabla': 'fact_metas_comerciales', 'transform': transformar_metas_comerciales, 'loader': 'fact_inc', 'delta_col': 'fecmes', 'pg_date_col': 'fecha_sk', 'depende_de': []},
    {'file': 'devoluciones_detalle_extractor.sql', 'tabla': 'fact_devoluciones', 'transform': transformar_devoluciones, 'loader': 'fact_inc', 'delta_col': 'e.fecfac', 'pg_date_col': 'fecha_sk', 'depende_de': ['dim_producto', 'dim_almacen', 'dim_sucursal', 'dim_vendedor']},
    # Auditoría 10: extractor validado desde antes (comentario propio del archivo) pero nunca
    # conectado a PIPELINE_CONFIG; Fact_Transferencias existía en el DDL con 0 filas.
    {'file': 'transferencias_extractor.sql', 'tabla': 'fact_transferencias', 'transform': transformar_transferencias, 'loader': 'fact_inc', 'delta_col': 'fecha', 'pg_date_col': 'fecha_sk', 'depende_de': ['dim_producto', 'dim_almacen', 'dim_sucursal']}
]

def validar_orden_pipeline(pipeline_config: list) -> None:
    """Auditoría 09 (H5): valida programáticamente que cada hecho declare sus dimensiones de
    dependencia ('depende_de') y que esas dimensiones aparezcan ANTES que el hecho en la lista.
    Lanza AssertionError si el orden es incorrecto, en vez de confiar únicamente en la
    disciplina de quien edite PIPELINE_CONFIG."""
    dims_vistas = set()
    for cfg in pipeline_config:
        if cfg.get('loader') in ('dim', 'scd2'):
            dims_vistas.add(cfg['tabla'])
        elif cfg.get('loader') == 'fact_inc':
            faltantes = [d for d in cfg.get('depende_de', []) if d not in dims_vistas]
            if faltantes:
                raise AssertionError(
                    f"PIPELINE_CONFIG mal ordenado: '{cfg['tabla']}' depende de {faltantes}, "
                    f"que no aparece(n) antes en la lista. Corrige el orden o 'depende_de'."
                )
    logger.info("Orden de PIPELINE_CONFIG validado: todas las dependencias dimensión->hecho preceden al hecho.")

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
        df_fecha = _leer_dim_cacheada(engine, 'dim_fecha', f"SELECT fecha_sk, fecha_completa FROM {schema}.dim_fecha")
        df_fecha['fecha_completa'] = pd.to_datetime(df_fecha['fecha_completa']).dt.date
        df['fecha_lookup'] = df[col_fecha_origen].dt.date
        df = df.merge(df_fecha, left_on='fecha_lookup', right_on='fecha_completa', how='left')
        df.drop(columns=['fecha_lookup', 'fecha_completa'], errors='ignore', inplace=True)
    
    # 2. Resolver producto_sk (codemp, codart)
    if 'codart' in df.columns:
        df_prod = _leer_dim_cacheada(engine, 'dim_producto', f"SELECT producto_sk, codemp, codart FROM {schema}.dim_producto WHERE es_vigente = TRUE")
        df = df.merge(df_prod, on=['codemp', 'codart'], how='left')

    # 3. Resolver cliente_sk (codcli -> hash_anonimo)
    if 'codcli' in df.columns:
        salt = pg.config.PII_SALT
        df['hash_anonimo'] = df['codcli'].apply(
            lambda x: hmac.new(salt.encode(), str(x).encode(), hashlib.sha256).hexdigest()
        )
        df_cli = _leer_dim_cacheada(engine, 'dim_cliente', f"SELECT cliente_sk, hash_anonimo FROM {schema}.dim_cliente WHERE es_vigente = TRUE")
        df = df.merge(df_cli, on=['hash_anonimo'], how='left')
        df.drop(columns=['hash_anonimo'], errors='ignore', inplace=True)

    # 4. Resolver proveedor_sk (codemp, codpro)
    if 'codpro' in df.columns:
        df_pro = _leer_dim_cacheada(engine, 'dim_proveedor', f"SELECT proveedor_sk, codemp, codpro FROM {schema}.dim_proveedor")
        df = df.merge(df_pro, on=['codemp', 'codpro'], how='left')

    # 5. Resolver vendedor_sk (codemp, codven)
    if 'codven' in df.columns:
        df_ven = _leer_dim_cacheada(engine, 'dim_vendedor', f"SELECT vendedor_sk, codemp, codven FROM {schema}.dim_vendedor")
        df = df.merge(df_ven, on=['codemp', 'codven'], how='left')

    # 6. Resolver empleado_sk (codemp, codemple)
    if 'codemple' in df.columns:
        df_emp = _leer_dim_cacheada(engine, 'dim_empleado', f"SELECT empleado_sk, codemp, codemple FROM {schema}.dim_empleado")
        df = df.merge(df_emp, on=['codemp', 'codemple'], how='left')

    # 7. Resolver usuario_sk (codemp, codusu)
    if 'codusu' in df.columns:
        df_usu = _leer_dim_cacheada(engine, 'dim_usuario', f"SELECT usuario_sk, codemp, codusu FROM {schema}.dim_usuario")
        df = df.merge(df_usu, on=['codemp', 'codusu'], how='left')

    # 8. Resolver formapago_sk (codemp, codforpag)
    if 'codforpag' in df.columns:
        df_fp = _leer_dim_cacheada(engine, 'dim_formapago', f"SELECT formapago_sk, codemp, codforpag FROM {schema}.dim_formapago")
        df = df.merge(df_fp, on=['codemp', 'codforpag'], how='left')

    # 9. Resolver almacen_sk (codemp, codalm)
    if 'codalm' in df.columns:
        df_alm = _leer_dim_cacheada(engine, 'dim_almacen', f"SELECT almacen_sk, codemp, codalm, establ FROM {schema}.dim_almacen")
        df = df.merge(df_alm, on=['codemp', 'codalm'], how='left', suffixes=('', '_alm'))
        if 'establ' not in df.columns and 'establ_alm' in df.columns:
            df['establ'] = df['establ_alm']
            df.drop(columns=['establ_alm'], errors='ignore', inplace=True)

    # 9b. Resolver almacen_origen_sk / almacen_destino_sk (fact_transferencias: dos FKs a la
    # misma dimensión, el resolver genérico de arriba solo cubre una columna 'codalm').
    if 'codalm_origen' in df.columns and 'codalm_destino' in df.columns:
        df_alm2 = _leer_dim_cacheada(engine, 'dim_almacen', f"SELECT almacen_sk, codemp, codalm FROM {schema}.dim_almacen")
        df = df.merge(
            df_alm2.rename(columns={'codalm': 'codalm_origen', 'almacen_sk': 'almacen_origen_sk'}),
            on=['codemp', 'codalm_origen'], how='left'
        )
        df = df.merge(
            df_alm2.rename(columns={'codalm': 'codalm_destino', 'almacen_sk': 'almacen_destino_sk'}),
            on=['codemp', 'codalm_destino'], how='left'
        )

    # 10. Resolver sucursal_sk (codemp, establ)
    if 'establ' in df.columns:
        df_suc = _leer_dim_cacheada(engine, 'dim_sucursal', f"SELECT sucursal_sk, codemp, establ FROM {schema}.dim_sucursal")
        df = df.merge(df_suc, on=['codemp', 'establ'], how='left')
    else:
        # No hay 'establ' en el hecho origen (no llegó vía dim_almacen): no se puede resolver
        # la sucursal real por join. Antes se tomaba una fila arbitraria (LIMIT 1) de
        # dim_sucursal y se la asignaba a TODAS las filas del chunk, atribuyendo transacciones
        # de sucursales distintas a una sola al azar. Ahora solo se usa el default explícito
        # -1 ("Desconocida") si existe; si no, sucursal_sk queda ausente y el bloque de abajo
        # lo reporta en vez de adivinar.
        df_suc_default = pd.read_sql(f"SELECT sucursal_sk FROM {schema}.dim_sucursal WHERE sucursal_sk = -1", engine)
        if not df_suc_default.empty:
            df['sucursal_sk'] = df_suc_default['sucursal_sk'].iloc[0]

    # 11. Resolver estado_documento_sk — junk dimension (tipo_documento, es_devolucion,
    # estado_factura). Auditoría 08 (F12) dejó el transformer exponiendo estos tres atributos
    # "para que el loader haga el lookup", pero ningún loader lo implementaba (fact_loader.py
    # solo hace INSERT/DELETE genéricos) — fact_ventas_detalle nunca pudo cargar por esto
    # (auditoría 10). A diferencia de las demás dimensiones (pobladas por su propio extractor),
    # dim_estado_documento solo trae el centinela -1 sembrado en el DDL (edw/02_dimensiones.sql);
    # las combinaciones reales se descubren y se upsertean aquí, desde los propios hechos.
    if {'tipo_documento', 'es_devolucion', 'estado_factura'}.issubset(df.columns):
        combos = df[['tipo_documento', 'es_devolucion', 'estado_factura']].drop_duplicates()
        if not combos.empty:
            insert_ed_sql = text(f"""
                INSERT INTO {schema}.dim_estado_documento (tipo_documento, es_devolucion, estado_factura)
                VALUES (:tipo_documento, :es_devolucion, :estado_factura)
                ON CONFLICT (tipo_documento, es_devolucion, estado_factura) DO NOTHING
            """)
            with engine.begin() as conn_ed:
                for _, fila in combos.iterrows():
                    conn_ed.execute(insert_ed_sql, {
                        "tipo_documento": fila['tipo_documento'],
                        "es_devolucion": bool(fila['es_devolucion']),
                        "estado_factura": fila['estado_factura'],
                    })
        df_ed = pd.read_sql(
            f"SELECT estado_documento_sk, tipo_documento, es_devolucion, estado_factura FROM {schema}.dim_estado_documento",
            engine
        )
        df = df.merge(df_ed, on=['tipo_documento', 'es_devolucion', 'estado_factura'], how='left')

    # Prevenir que haya nulos en SKs obligatorios: solo se rellena con el default explícito -1
    # ("Desconocido/a") si existe en la dimensión. Antes, si no había fila -1, se tomaba una fila
    # arbitraria (LIMIT 1) de la dimensión y se la asignaba silenciosamente -- podía atribuir la
    # transacción a un cliente/producto/sucursal equivocado sin ningún aviso. Ahora, si no hay
    # default, se deja el nulo y se reporta cuántas filas quedaron sin resolver.
    for sk_col in ['fecha_sk', 'producto_sk', 'cliente_sk', 'sucursal_sk', 'vendedor_sk', 'formapago_sk', 'proveedor_sk', 'almacen_sk', 'empleado_sk', 'usuario_sk', 'estado_documento_sk', 'almacen_origen_sk', 'almacen_destino_sk']:
        if sk_col in df.columns:
            n_nulos = int(df[sk_col].isnull().sum())
            if n_nulos:
                try:
                    p_engine = pg.connect()
                    # Auditoría 09 (H7): mapeo único DIM_TABLE_BY_SK reutilizado aquí y en la
                    # validación de dependencias, en vez de una cadena de elif duplicada.
                    p_tbl = DIM_TABLE_BY_SK.get(sk_col, sk_col.replace('_sk', ''))

                    sk_default = pd.read_sql(f"SELECT {sk_col} FROM {schema}.{p_tbl} WHERE {sk_col} = -1", p_engine)
                    if not sk_default.empty:
                        df[sk_col] = df[sk_col].fillna(int(sk_default[sk_col].iloc[0]))
                        logger.warning(f"{tbl_destino}: {n_nulos} filas sin {sk_col} resuelto, rellenadas con el default -1.")
                    else:
                        logger.warning(
                            f"{tbl_destino}: {n_nulos} filas sin {sk_col} resuelto y sin fila default "
                            f"-1 en {p_tbl}; quedan NULL (no se adivina una fila al azar)."
                        )
                except Exception as ex_def:
                    logger.warning(f"No se pudo resolver default para {sk_col}: {ex_def}")

    # Asegurar tipo de dato entero
    for col in df.columns:
        if col.endswith('_sk'):
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(-1).astype(int)

    return df

def load_data_chunk(pg: PostgresConnector, df_transformed: pd.DataFrame, config_item: dict, conn=None) -> int:
    """Auditoría 09 (H4): 'conn' se propaga para que todos los chunks de una misma tabla (y su
    DELETE de idempotencia previo) compartan una única transacción atómica."""
    l_type = config_item['loader']
    if l_type == 'dim':
        return load_dimension(pg, df_transformed, config_item['tabla'], config_item['keys'], conn=conn)
    elif l_type == 'scd2':
        return load_dim_scd2(pg, df_transformed, config_item['tabla'], config_item['keys'], config_item.get('desc_col'), conn=conn)
    else:
        return load_facts_append_only(pg, df_transformed, config_item['tabla'], conn=conn)

# Auditoría 09 (H9): identificador fijo y arbitrario del lock de sesión de PostgreSQL que
# garantiza una sola ejecución activa de este pipeline a la vez.
LOCK_ID_PIPELINE = 823141

def run_etl(config: ETLConfig, tablas_incluir: list = None) -> None:
    """Ejecuta el pipeline ETL completo.

    Auditoría 09 (H8): `tablas_incluir` permite correr un subconjunto puntual de
    PIPELINE_CONFIG (por nombre de tabla destino) en vez de siempre las 19 tablas completas —
    útil para depurar o reprocesar una tabla puntual sin tocar PIPELINE_CONFIG.
    """
    inicio = datetime.now()
    logger.info(f"=== INICIO DEL PIPELINE ETL PROD - {inicio} ===")

    # Precondición de seguridad: salt PII robusto (privacidad de datos de cliente).
    validar_configuracion(config)
    # Auditoría 09 (H5): valida que ningún hecho preceda a sus dimensiones de dependencia.
    validar_orden_pipeline(PIPELINE_CONFIG)
    # Reiniciar caché de dimensiones y contadores de esta corrida.
    _DIM_CACHE.clear()
    _STATS_CONTROL['fallas'] = 0

    pg = PostgresConnector(config)
    sa = SQLAnywhereConnector(config)
    schema = config.PG_SCHEMA
    extractors_path = os.path.join(os.path.dirname(__file__), 'extractors')
    tablas_ok, tablas_fail, tablas_saltadas = 0, 0, 0
    dims_fallidas: set = set()  # Auditoría 09 (H3)

    pipeline_a_correr = PIPELINE_CONFIG
    if tablas_incluir:
        pipeline_a_correr = [c for c in PIPELINE_CONFIG if c['tabla'] in tablas_incluir]
        no_encontradas = set(tablas_incluir) - {c['tabla'] for c in pipeline_a_correr}
        if no_encontradas:
            logger.warning(f"tablas_incluir contiene nombres no presentes en PIPELINE_CONFIG: {no_encontradas}")
        logger.info(f"Ejecutando subconjunto de tablas: {[c['tabla'] for c in pipeline_a_correr]}")

    lock_conn = None
    lock_adquirido = False
    try:
        sa.connect()
        pg.connect()

        # Auditoría 09 (H9): lock de sesión — si otra corrida ya lo tiene, abortar de
        # inmediato en vez de arriesgar un DELETE/INSERT concurrente sobre la misma tabla.
        lock_conn = pg.connect().connect()
        lock_adquirido = bool(lock_conn.execute(text("SELECT pg_try_advisory_lock(:id)"), {"id": LOCK_ID_PIPELINE}).scalar())
        if not lock_adquirido:
            logger.critical(
                "No se pudo adquirir el lock del pipeline (id=%s): ya hay otra corrida activa. Abortando.",
                LOCK_ID_PIPELINE
            )
            return

        asegurar_registros_desconocidos(pg)

        # 1. Dimensión Tiempo
        logger.info("Generando Dimensión Fecha...")
        df_fecha = generar_dim_tiempo(config.DIM_TIEMPO_DESDE, config.DIM_TIEMPO_HASTA)
        pg.load_dataframe(df_fecha, 'dim_fecha', 'upsert', claves_negocio=['fecha_completa'])
        logger.info("Dimensión Tiempo actualizada exitosamente.")

        # 2. Extractores Modulares
        for cfg in pipeline_a_correr:
            sql_file = os.path.join(extractors_path, cfg['file'])
            if not os.path.isfile(sql_file):
                logger.warning(f"Archivo extractor SQL '{cfg['file']}' no encontrado, saltando...")
                continue

            start_t_table = datetime.now()
            es_hecho = cfg.get('loader') == 'fact_inc'
            es_dim = cfg.get('loader') in ('dim', 'scd2')

            # Auditoría 09 (H3): si el hecho depende de una dimensión que falló en ESTA misma
            # corrida, no procesarlo como si nada — quedaría resolviendo llaves contra una
            # dimensión incompleta y atribuyendo filas al centinela -1 sin ser un caso real de
            # llave huérfana. Se marca SKIPPED explícitamente en vez de FAIL o SUCCESS.
            if es_hecho:
                dependencias_fallidas = set(cfg.get('depende_de', [])) & dims_fallidas
                if dependencias_fallidas:
                    logger.warning(
                        f"[SKIPPED] {cfg['tabla']}: depende de {sorted(dependencias_fallidas)}, "
                        f"que falló en esta corrida. No se procesa para no atribuir filas a un "
                        f"centinela -1 por una dimensión incompleta."
                    )
                    registrar_control_etl(pg, cfg['tabla'], 0, 'SKIPPED',
                                          f"Dependencia fallida: {sorted(dependencias_fallidas)}", 0)
                    tablas_saltadas += 1
                    continue

            # --- Aislamiento de errores por tabla (P10): una tabla que falla no aborta el pipeline ---
            try:
                with open(sql_file, 'r', encoding='utf-8') as f:
                    sql_raw = f.read()

                # Determinar el piso de fecha de extracción.
                last_date = get_last_etl_date(pg, cfg['tabla'])
                incremental = config.MODO_INCREMENTAL and es_hecho and last_date.year > 1900
                fecha_desde = last_date.strftime('%Y-%m-%d') if incremental else config.FECHA_HISTORICA
                logger.info(f"Extracción {cfg['tabla']} | modo={'INCREMENTAL' if incremental else 'FULL'} | fecha_desde >= {fecha_desde}")

                # Render de tokens {CODEMP}/{ESTADO}/{FECHA_DESDE}. Robusto ante UNION ALL:
                # cada rama trae su propio token en su WHERE (corrige el antiguo replace(';', ...)).
                sql_query = render_sql(sql_raw, config, fecha_desde)
                pg_date_col = cfg.get('pg_date_col', 'fecha_sk')

                total_loaded = 0
                total_extraido = 0
                chunk_idx = 1

                # Auditoría 09 (H4): el DELETE de idempotencia y TODOS los chunks de esta tabla
                # comparten una única transacción. Si un chunk intermedio falla, la excepción
                # revierte también el DELETE, dejando la tabla en su estado anterior (consistente)
                # en vez de en un estado a medias hasta la siguiente corrida.
                with pg.connect().begin() as conn_tabla:
                    if cfg.get('snapshot'):
                        # Hecho tipo snapshot (foto diaria): reemplazar SOLO la foto de HOY,
                        # preservando el histórico de días anteriores.
                        hoy = date.today().strftime('%Y-%m-%d')
                        delete_sql = (
                            f"DELETE FROM {schema}.{cfg['tabla']} "
                            f"WHERE {pg_date_col} IN "
                            f"(SELECT fecha_sk FROM {schema}.dim_fecha WHERE fecha_completa = :hoy)"
                        )
                        res = conn_tabla.execute(text(delete_sql), {"hoy": hoy})
                        logger.info(f"Snapshot: {res.rowcount} filas de hoy ({hoy}) reemplazadas en {cfg['tabla']}.")
                    elif incremental:
                        # Hecho transaccional: borrar el rango a recargar para evitar duplicados.
                        delete_sql = (
                            f"DELETE FROM {schema}.{cfg['tabla']} "
                            f"WHERE {pg_date_col} IN "
                            f"(SELECT fecha_sk FROM {schema}.dim_fecha WHERE fecha_completa >= :desde)"
                        )
                        res = conn_tabla.execute(text(delete_sql), {"desde": fecha_desde})
                        logger.info(f"Idempotencia: {res.rowcount} registros eliminados en {cfg['tabla']} (fecha >= {fecha_desde}).")

                    for df_chunk in sa.yield_query_chunks(sql_query, chunksize=config.BATCH_SIZE):
                        logger.info(f"Procesando Chunk #{chunk_idx} ({len(df_chunk)} registros)...")
                        total_extraido += len(df_chunk)
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

                            # El lookup PII vive en public.cliente_lookup, fuera de esta
                            # transacción (schema/tabla distintos): se comitea aparte.
                            original_schema = pg.config.PG_SCHEMA
                            pg.config.PG_SCHEMA = SCHEMA_PUBLICO_LOOKUP
                            pg.load_dataframe(df_lookup, tabla='cliente_lookup', modo='upsert', claves_negocio=['hash_anonimo'])
                            pg.config.PG_SCHEMA = original_schema

                            df_chunk.drop(columns=['ruc_cedula', 'nombre_cliente', 'codcli'], errors='ignore', inplace=True)
                        # ---------------------------------------------

                        if cfg.get('loader') not in ['dim', 'scd2']:
                            df_chunk = resolver_llaves_hecho(pg, df_chunk, cfg['tabla'])

                        loaded_records = load_data_chunk(pg, df_chunk, cfg, conn=conn_tabla)
                        total_loaded += loaded_records
                        chunk_idx += 1

                # Auditoría 09 (H10): reconciliación mínima entre lo extraído y lo cargado, para
                # que una pérdida de filas silenciosa (más allá de los _sk nulos ya advertidos)
                # sea visible en el resumen de la tabla, no solo si se revisan los logs línea a línea.
                if total_extraido and total_loaded != total_extraido:
                    logger.warning(
                        f"{cfg['tabla']}: extraídas {total_extraido} filas de SAP pero cargadas "
                        f"{total_loaded} en el EDW (diferencia {total_extraido - total_loaded}). "
                        f"Puede ser esperado (upsert/SCD2 dedup) o una pérdida real — revisar."
                    )

                dur_table = int((datetime.now() - start_t_table).total_seconds())
                registrar_control_etl(pg, cfg['tabla'], total_loaded, 'SUCCESS',
                                      f"OK modo={'INC' if incremental else 'FULL'} desde={fecha_desde} extraidas={total_extraido}", dur_table)
                logger.info(f"[OK] FINALIZADO {cfg['tabla']}: {total_loaded} registros en {dur_table} segs.")
                tablas_ok += 1

            except Exception as e_tbl:
                dur_table = int((datetime.now() - start_t_table).total_seconds())
                logger.error(f"[ERROR] Falla en tabla {cfg['tabla']}: {e_tbl}", exc_info=True)
                registrar_control_etl(pg, cfg['tabla'], 0, 'FAIL', str(e_tbl)[:500], dur_table)
                tablas_fail += 1
                if es_dim:
                    dims_fallidas.add(cfg['tabla'])
                continue  # Aislar el fallo: continuar con las demás tablas.

        logger.info(
            f"Resumen pipeline: {tablas_ok} tablas OK, {tablas_fail} con fallo, "
            f"{tablas_saltadas} saltadas por dependencia fallida, "
            f"{_STATS_CONTROL['fallas']} fallas de control (edw.etl_control)."
        )

    except Exception as e:
        logger.critical(f"Falla crítica (infraestructura/conexión): {e}", exc_info=True)
        registrar_control_etl(pg, 'PIPELINE_GENERAL', 0, 'FAIL', str(e), 0)
        raise
    finally:
        if lock_conn is not None:
            try:
                if lock_adquirido:
                    lock_conn.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": LOCK_ID_PIPELINE})
            finally:
                lock_conn.close()
        sa.disconnect()
        pg.disconnect()
        duracion = int((datetime.now() - inicio).total_seconds())
        logger.info(f"=== FIN PIPELINE ETL - Duración: {duracion} segs ===")

if __name__ == "__main__":
    # Auditoría 09 (H8): --tablas permite reprocesar/depurar una tabla puntual sin editar
    # PIPELINE_CONFIG (ej: python orchestrator.py --tablas dim_producto fact_ventas_detalle).
    parser = argparse.ArgumentParser(description="Orquestador del pipeline ETL SAP -> EDW.")
    parser.add_argument('--tablas', nargs='+', default=None,
                        help="Nombres de tabla_destino de PIPELINE_CONFIG a ejecutar (por defecto, todas).")
    args = parser.parse_args()

    logger.info("Cargando variables...")
    config = ETLConfig()
    run_etl(config, tablas_incluir=args.tablas)