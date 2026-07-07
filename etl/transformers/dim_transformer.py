# transformers/dim_transformer.py
import pandas as pd
import numpy as np
from transformers.dim_tiempo import normalizar_fechas, normalizar_numericos, normalizar_strings

ESTADO_MAP = {'A': 'A', 'I': 'I', 'S': 'S', 'E': 'E', 
              '1': 'A', '0': 'I', 'ACTIVO': 'A', 'INACTIVO': 'I'}

def normalizar_estado(df: pd.DataFrame, col: str) -> pd.DataFrame:
    df[col] = df[col].astype(str).str.strip().str.upper().map(ESTADO_MAP).fillna('A')
    return df

TIPO_ID_MAP = {'04': 'RUC', '05': 'CEDULA', '06': 'PASAPORTE',
               '07': 'CONSUMIDOR_FINAL', '08': 'ID_EXTERIOR'}

def normalizar_tipo_id(df: pd.DataFrame, col: str) -> pd.DataFrame:
    df[col] = df[col].astype(str).str.strip().map(TIPO_ID_MAP).fillna('OTRO')
    return df

def deduplicar(df: pd.DataFrame, clave_natural: list) -> pd.DataFrame:
    """Conserva el registro más reciente basado en la fecha de modificación."""
    if 'fecult' in df.columns:
        df = df.sort_values('fecult', ascending=False)
    df = df.drop_duplicates(subset=clave_natural, keep='first')
    return df

def transformar_clientes(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar_strings(df, ['codcli', 'codemp', 'nombre_cliente', 'ruc_cedula', 'tipo_id', 
                                 'clase_cliente', 'nombre_clase', 'zona', 'nombre_zona', 'ciudad', 'estado', 'sexo'])
    df = normalizar_numericos(df, ['limite_credito', 'dias_credito'])
    df = normalizar_estado(df, 'estado')
    df = normalizar_tipo_id(df, 'tipo_id')
    
    # Valores SCD-2 predeterminados si faltan
    if 'fecha_inicio_vigencia' not in df.columns:
        df['fecha_inicio_vigencia'] = pd.Timestamp.now().date()
    if 'fecha_fin_vigencia' not in df.columns:
        df['fecha_fin_vigencia'] = pd.NaT
    if 'es_vigente' not in df.columns:
        df['es_vigente'] = True
        
    return df

def transformar_productos(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar_strings(df, ['codemp', 'codart', 'nombre_articulo', 'clase', 'nombre_clase', 
                                 'subclase', 'nombre_subclase', 'unidad', 'nombre_unidad', 'estado'])
    df = normalizar_numericos(df, ['precio_oficial', 'costo_promedio'])
    df = normalizar_estado(df, 'estado')
    
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

def transformar_sucursales(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar_strings(df, ['codemp', 'establ', 'codigo_sucursal', 'nombre_sucursal', 'direccion', 'telefono'])
    if 'activa' in df.columns:
        df['activa'] = df['activa'].astype(str).str.strip().str.upper().isin(['1', 'T', 'TRUE', 'A', 'ACTIVO', 'S'])
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
        df['activo'] = df['activo'].astype(str).str.strip().str.upper().isin(['1', 'T', 'TRUE', 'A', 'ACTIVO', 'S'])
    else:
        df['activo'] = True
    return df

def transformar_empleados(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar_strings(df, ['codemp', 'codemple', 'nombre_empleado', 'cedula', 'cargo', 'departamento'])
    df = normalizar_numericos(df, ['sueldo_base'])
    df = normalizar_fechas(df, ['fecha_ingreso'])
    if 'activo' in df.columns:
        df['activo'] = df['activo'].astype(str).str.strip().str.upper().isin(['1', 'T', 'TRUE', 'A', 'ACTIVO', 'S'])
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

def transformar_geografia(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar_strings(df, ['pais', 'provincia', 'canton', 'parroquia'])
    return df
