# transformers/dim_tiempo.py
import pandas as pd
import numpy as np

def generar_dim_tiempo(fecha_inicio: str = '2010-01-01',
                       fecha_fin:    str = '2030-12-31') -> pd.DataFrame:
    """Genera la tabla Dim_Tiempo completa de forma algorítmica."""
    MESES_ES = {
        1:'Enero', 2:'Febrero', 3:'Marzo', 4:'Abril', 5:'Mayo',
        6:'Junio', 7:'Julio', 8:'Agosto', 9:'Septiembre',
        10:'Octubre', 11:'Noviembre', 12:'Diciembre'
    }
    DIAS_ES  = {
        0:'Lunes', 1:'Martes', 2:'Miércoles', 3:'Jueves',
        4:'Viernes', 5:'Sábado', 6:'Domingo'
    }

    fechas = pd.date_range(start=fecha_inicio, end=fecha_fin, freq='D')
    df = pd.DataFrame({'fecha_completa': fechas})

    df['anio']         = df.fecha_completa.dt.year
    df['trimestre']    = df.fecha_completa.dt.quarter
    df['mes']          = df.fecha_completa.dt.month
    df['nombre_mes']   = df.mes.map(MESES_ES)
    df['semana_anio']  = df.fecha_completa.dt.isocalendar().week.astype(int)
    df['dia_mes']      = df.fecha_completa.dt.day
    df['dia_semana']   = df.fecha_completa.dt.dayofweek + 1    # 1=Lun..7=Dom
    df['nombre_dia']   = (df.fecha_completa.dt.dayofweek).map(DIAS_ES)
    df['es_fin_semana']= df.fecha_completa.dt.dayofweek >= 5
    df['semestre']     = np.where(df.mes <= 6, 1, 2)
    df['periodo_fiscal']= df.anio.astype(str) + '-Q' + df.trimestre.astype(str)
    df['es_feriado']   = False    # Poblar con calendario local si fuera necesario

    return df

def normalizar_fechas(df: pd.DataFrame, columnas_fecha: list) -> pd.DataFrame:
    """Convierte columnas al tipo datetime64 de forma segura."""
    for col in columnas_fecha:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
            df.loc[df[col] < pd.Timestamp('2000-01-01'), col] = pd.NaT
    return df

def normalizar_numericos(df: pd.DataFrame, columnas_num: list) -> pd.DataFrame:
    """Reemplaza nulos y redondea valores numéricos."""
    for col in columnas_num:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
            df[col] = df[col].round(4)
    return df

def normalizar_strings(df: pd.DataFrame, columnas_str: list) -> pd.DataFrame:
    """Elimina espacios extra y normaliza strings vacíos."""
    for col in columnas_str:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.upper()
            df[col] = df[col].replace({'NAN': None, 'NONE': None, '': None})
    return df
