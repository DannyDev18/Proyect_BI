# transformers/dim_transformer.py
import logging
import pandas as pd
import numpy as np
from transformers.dim_tiempo import normalizar_fechas, normalizar_numericos, normalizar_strings

logger = logging.getLogger("ETLOrchestrator")

ESTADO_MAP = {'A': 'A', 'I': 'I', 'S': 'S', 'E': 'E',
              '1': 'A', '0': 'I', 'ACTIVO': 'A', 'INACTIVO': 'I'}

def normalizar_estado(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Auditoría 08 (F6): distingue 'no vino estado' (NULL real) de 'vino un código no
    mapeado' y loguea ambos casos por separado antes de aplicar el fallback a 'A' (Activo),
    en vez de asumirlo en silencio."""
    original_nulo = df[col].isna()
    mapeado = df[col].astype(str).str.strip().str.upper().map(ESTADO_MAP)
    cayo_en_fallback = mapeado.isna()
    n_nulos = int((original_nulo & cayo_en_fallback).sum())
    n_no_mapeados = int((~original_nulo & cayo_en_fallback).sum())
    if n_nulos:
        logger.warning("normalizar_estado: %s filas de '%s' con estado NULL -> 'A' por defecto", n_nulos, col)
    if n_no_mapeados:
        logger.warning("normalizar_estado: %s filas de '%s' con código no mapeado -> 'A' por defecto", n_no_mapeados, col)
    df[col] = mapeado.fillna('A')
    return df

TIPO_ID_MAP = {'04': 'RUC', '05': 'CEDULA', '06': 'PASAPORTE',
               '07': 'CONSUMIDOR_FINAL', '08': 'ID_EXTERIOR'}

def normalizar_tipo_id(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Auditoría 08 (F7): las claves de TIPO_ID_MAP son códigos de 2 dígitos ('04'..'08'); si
    la columna llegó como numérico (p.ej. 4 en vez de '04') se rellena con ceros a la
    izquierda antes de mapear, para no perder la clasificación por un cero perdido."""
    valores = df[col].astype(str).str.strip()
    if pd.api.types.is_numeric_dtype(df[col]):
        valores = valores.str.zfill(2)
    df[col] = valores.map(TIPO_ID_MAP).fillna('OTRO')
    return df

def deduplicar(df: pd.DataFrame, clave_natural: list) -> pd.DataFrame:
    """Conserva el registro más reciente basado en la fecha de modificación.

    Auditoría 08 (F9): se agrega la propia clave natural como desempate secundario estable
    para que el resultado sea determinista cuando 'fecult' es nulo o está repetido entre
    duplicados.
    """
    columnas_orden = (['fecult'] if 'fecult' in df.columns else []) + clave_natural
    ascendente = ([False] if 'fecult' in df.columns else []) + [True] * len(clave_natural)
    df = df.sort_values(columnas_orden, ascending=ascendente, na_position='last')
    df = df.drop_duplicates(subset=clave_natural, keep='first')
    return df

def transformar_clientes(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar_strings(df, ['codcli', 'codemp', 'nombre_cliente', 'ruc_cedula', 'tipo_id', 
                                 'clase_cliente', 'nombre_clase', 'zona', 'nombre_zona', 'ciudad', 'estado', 'sexo'])
    df = normalizar_numericos(df, ['limite_credito', 'dias_credito'])
    df = normalizar_estado(df, 'estado')
    df = normalizar_tipo_id(df, 'tipo_id')
    # Auditoría 08 (F8): sin este paso, dos filas para el mismo (codemp, codcli) llegarían
    # al loader como candidatas "vigentes" y violarían el índice único parcial de SCD2.
    df = deduplicar(df, clave_natural=['codemp', 'codcli'])

    # Valores SCD-2 predeterminados si faltan
    if 'fecha_inicio_vigencia' not in df.columns:
        df['fecha_inicio_vigencia'] = pd.Timestamp.now().date()
    if 'fecha_fin_vigencia' not in df.columns:
        df['fecha_fin_vigencia'] = pd.NaT
    if 'es_vigente' not in df.columns:
        df['es_vigente'] = True
        
    return df

def transformar_productos(df: pd.DataFrame) -> pd.DataFrame:
    # Auditoría 34: 'ultcos' es el ÚLTIMO costo, no un promedio -- el extractor ahora lo
    # trae con el alias correcto ('ultimo_costo'), pero la columna del DW se conserva
    # como 'costo_promedio' (edw.dim_producto.costo_promedio) para no alterar el
    # esquema; se renombra aquí, igual que fact_transformer.py hace con 'numfac'.
    df = df.rename(columns={'ultimo_costo': 'costo_promedio'})

    df = normalizar_strings(df, ['codemp', 'codart', 'nombre_articulo', 'clase', 'nombre_clase',
                                 'subclase', 'nombre_subclase', 'unidad', 'nombre_unidad', 'estado'])
    df = normalizar_numericos(df, ['precio_oficial', 'costo_promedio'])
    df = normalizar_estado(df, 'estado')
    # Auditoría 08 (F8): mismo riesgo de violar el índice único parcial SCD2 que en clientes.
    df = deduplicar(df, clave_natural=['codemp', 'codart'])

    # Auditoría 34 (H-13): 'es_servicio' NO se deriva de articulos.bienser -- ese flag del
    # maestro de artículo casi no se usa en Producción (1 fila en 'S' de 8.152, auditoría
    # 34 §11.3-bis). La clasificación real bien/servicio vive por LÍNEA de transacción
    # (renglonesfacturas.bienser, 58.407 líneas 'S' reales) y se resuelve a nivel de
    # fact_ventas_detalle (fact_transformer.transformar_ventas_detalle), no aquí. Este
    # campo de dim_producto queda como atributo informativo de catálogo, no como fuente
    # de verdad para el motor de comisiones variables (commission_engine usa el campo de
    # la línea, no el del producto).
    if 'es_servicio' not in df.columns:
        df['es_servicio'] = False

    # SCD-2
    if 'fecha_inicio_vigencia' not in df.columns:
        df['fecha_inicio_vigencia'] = pd.Timestamp.now().date()
    if 'fecha_fin_vigencia' not in df.columns:
        df['fecha_fin_vigencia'] = pd.NaT
    if 'es_vigente' not in df.columns:
        df['es_vigente'] = True

    return df

VALORES_BOOLEANOS_ACTIVO = ['1', 'T', 'TRUE', 'A', 'ACTIVO', 'S']

def normalizar_booleano_activo(serie: pd.Series) -> pd.Series:
    """Auditoría 08 (F10): si la columna llega como float (1.0 en vez de 1), astype(str)
    produce '1.0', que no está en VALORES_BOOLEANOS_ACTIVO. Se normaliza a numérico primero
    cuando es posible para no perder banderas 'activo' reales."""
    numerico = pd.to_numeric(serie, errors='coerce')
    es_numerico = numerico.notna()
    texto = serie.astype(str).str.strip().str.upper()
    resultado = texto.isin(VALORES_BOOLEANOS_ACTIVO)
    resultado[es_numerico] = numerico[es_numerico] == 1
    return resultado

def transformar_sucursales(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar_strings(df, ['codemp', 'establ', 'codigo_sucursal', 'nombre_sucursal', 'direccion', 'telefono'])
    if 'activa' in df.columns:
        df['activa'] = normalizar_booleano_activo(df['activa'])
    else:
        df['activa'] = True
    return df

def transformar_almacenes(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar_strings(df, ['codemp', 'codalm', 'nombre_almacen', 'establ'])
    return df

def transformar_proveedores(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar_strings(df, ['codemp', 'codpro', 'nombre_proveedor', 'ruc', 'ciudad', 'estado'])
    df = normalizar_numericos(df, ['dias_credito'])
    df = normalizar_estado(df, 'estado')
    return df

def transformar_vendedores(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar_strings(df, ['codemp', 'codven', 'nombre_vendedor'])
    df = normalizar_numericos(df, ['comision'])
    if 'activo' in df.columns:
        df['activo'] = normalizar_booleano_activo(df['activo'])
    else:
        df['activo'] = True
    return df

def transformar_empleados(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar_strings(df, ['codemp', 'codemple', 'nombre_empleado', 'cedula', 'cargo', 'departamento'])
    df = normalizar_numericos(df, ['sueldo_base'])
    df = normalizar_fechas(df, ['fecha_ingreso'])
    if 'activo' in df.columns:
        df['activo'] = normalizar_booleano_activo(df['activo'])
    else:
        df['activo'] = True
    return df

def transformar_usuarios(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar_strings(df, ['codemp', 'codusu', 'nombre_usuario', 'rol', 'estado'])
    return df

def transformar_formapago(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar_strings(df, ['codemp', 'codforpag', 'nombre_forma_pago'])
    df = normalizar_numericos(df, ['dias_plazo'])
    return df
