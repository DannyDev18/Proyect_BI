# transformers/dim_tiempo.py
import logging
import pandas as pd
import numpy as np

logger = logging.getLogger("ETLOrchestrator")

# Auditoría 08 (F1): el corte de fechas válidas debe alinearse al rango real de Dim_Fecha,
# no a un valor arbitrario. Mismo default que generar_dim_tiempo().
FECHA_MINIMA_DIM_TIEMPO = pd.Timestamp('2010-01-01')

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

def normalizar_fechas(df: pd.DataFrame, columnas_fecha: list,
                       fecha_minima: pd.Timestamp = FECHA_MINIMA_DIM_TIEMPO) -> pd.DataFrame:
    """Convierte columnas al tipo datetime64 de forma segura.

    Auditoría 08 (F1): el corte usa fecha_minima (alineado al rango real de Dim_Fecha) en
    vez de un valor hardcodeado; se loguea cuántas filas se anulan por esta regla.
    """
    for col in columnas_fecha:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
            fuera_de_rango = df[col] < fecha_minima
            n_anuladas = int(fuera_de_rango.sum())
            if n_anuladas:
                logger.warning(
                    "normalizar_fechas: %s filas de '%s' anuladas por ser anteriores a %s",
                    n_anuladas, col, fecha_minima.date()
                )
            df.loc[fuera_de_rango, col] = pd.NaT
    return df

def normalizar_numericos(df: pd.DataFrame, columnas_num: list,
                          permitir_nulos: list = None) -> pd.DataFrame:
    """Convierte a numérico y redondea.

    Auditoría 08 (F2): 'ausente/no parseable' no es lo mismo que 'cero'. Las columnas listadas
    en permitir_nulos conservan NaN en vez de rellenarse con 0.0 (usar para costos/precios que
    alimentan cálculos derivados, p.ej. márgenes). Para el resto se mantiene fillna(0.0) mas se
    loguea cuántas filas fueron rellenadas.
    """
    permitir_nulos = permitir_nulos or []
    for col in columnas_num:
        if col in df.columns:
            valores = pd.to_numeric(df[col], errors='coerce')
            if col in permitir_nulos:
                df[col] = valores.round(4)
            else:
                n_rellenadas = int(valores.isna().sum())
                if n_rellenadas:
                    logger.warning(
                        "normalizar_numericos: %s filas de '%s' ausentes/no parseables "
                        "rellenadas con 0.0", n_rellenadas, col
                    )
                df[col] = valores.fillna(0.0).round(4)
    return df

def normalizar_strings(df: pd.DataFrame, columnas_str: list) -> pd.DataFrame:
    """Elimina espacios extra y normaliza strings vacíos.

    Auditoría 08 (F4): si una columna de código de negocio llega con dtype numérico (el driver
    infirió tipo desde un VARCHAR solo-dígitos), astype(str) pierde ceros a la izquierda antes de
    esta función. No se puede reconstruir el ancho original aquí, así que se loguea la situación
    para que se corrija en el extractor/conector en vez de fallar en silencio.
    """
    for col in columnas_str:
        if col in df.columns:
            if pd.api.types.is_numeric_dtype(df[col]):
                logger.warning(
                    "normalizar_strings: '%s' llegó con dtype numérico (%s); si es un código de "
                    "negocio (codalm, codemp, establ, etc.) pudo perder ceros a la izquierda "
                    "antes de esta conversión — revisar el extractor/conector de origen.",
                    col, df[col].dtype
                )
            df[col] = df[col].astype(str).str.strip().str.upper()
            df[col] = df[col].replace({'NAN': None, 'NONE': None, '': None})
    return df
