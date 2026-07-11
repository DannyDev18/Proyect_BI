# ml/src/preprocessor.py
import pandas as pd
import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

# Feriados nacionales de fecha fija en Ecuador (Dim_Fecha.es_feriado nunca se puebla en el
# EDW -- ver transformers/dim_tiempo.py: "Poblar con calendario local si fuera necesario").
FERIADOS_ECUADOR_FECHA_FIJA = {(1, 1), (5, 1), (5, 24), (7, 24), (8, 10), (10, 9), (11, 2), (11, 3), (12, 25)}


def _domingo_pascua(anio: int) -> pd.Timestamp:
    """Algoritmo del computus gregoriano (Gauss) para el domingo de Pascua."""
    a, b, c = anio % 19, anio // 100, anio % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return pd.Timestamp(year=anio, month=mes, day=dia)


def _feriados_movibles_ecuador(anio: int) -> set:
    """Viernes Santo (Pascua - 2 días) y Carnaval lunes/martes (Pascua - 48/-47 días).
    v0.1.0 solo cubría feriados de fecha fija -- ver
    docs/auditoria/21_mejora_features_ventas_y_granularidad.md."""
    pascua = _domingo_pascua(anio)
    viernes_santo = pascua - pd.Timedelta(days=2)
    carnaval_lunes = pascua - pd.Timedelta(days=48)
    carnaval_martes = pascua - pd.Timedelta(days=47)
    return {
        (viernes_santo.month, viernes_santo.day),
        (carnaval_lunes.month, carnaval_lunes.day),
        (carnaval_martes.month, carnaval_martes.day),
    }


# Columnas exógenas que fetch_daily_sales() calcula del MISMO día que el target
# (n_facturas/n_clientes/ticket_promedio se derivan de las mismas transacciones que
# y_sales_net). Usarlas tal cual sería fuga de datos (en producción no se conocen hasta
# que el día termina); se rezagan 1 día para que sean predictoras legítimas.
# ticket_promedio se calcula en el transformer (no viene de la SQL) antes de rezagarla.
COLUMNAS_EXOGENAS_CONTEMPORANEAS = ['n_clientes', 'n_facturas', 'pct_descuento_prom', 'ticket_promedio']


class TimeSeriesLagsTransformer(BaseEstimator, TransformerMixin):
    """
    Genera Features de lags e informaciones temporales básicas.
    Para modelos de MLOps de tabla (Random Forest) que no tienen memoria temporal nativa,
    pasamos las medidas pasadas como columnas en el mismo registro.
    """
    def __init__(self, target_col='y_sales_net', lags=(1, 7, 30)):
        self.target_col = target_col
        self.lags = lags

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        X_out = X.copy()
        
        if 'producto' in X_out.columns:
            # Generar Lags agrupados por producto
            for lag in self.lags:
                col_name = f'lag_{lag}_{self.target_col}'
                X_out[col_name] = X_out.groupby('producto')[self.target_col].shift(lag)
            # Agregar métricas agrupadas
            gb = X_out.groupby('producto')[self.target_col]
            X_out['rolling_mean_7d'] = gb.transform(lambda x: x.shift(1).rolling(window=7, min_periods=1).mean())
            X_out['rolling_mean_30d'] = gb.transform(lambda x: x.shift(1).rolling(window=30, min_periods=1).mean())
            X_out['rolling_std_7d'] = gb.transform(lambda x: x.shift(1).rolling(window=7, min_periods=1).std())
            X_out['rolling_min_7d'] = gb.transform(lambda x: x.shift(1).rolling(window=7, min_periods=1).min())
            X_out['rolling_max_7d'] = gb.transform(lambda x: x.shift(1).rolling(window=7, min_periods=1).max())
            X_out['expanding_mean'] = gb.transform(lambda x: x.shift(1).expanding().mean())
        else:
            # Generar Lags directos sobre el set global (ej. Ventas Generales)
            for lag in self.lags:
                col_name = f'lag_{lag}_{self.target_col}'
                X_out[col_name] = X_out[self.target_col].shift(lag)
            
            y_shift = X_out[self.target_col].shift(1)
            X_out['rolling_mean_7d'] = y_shift.rolling(window=7, min_periods=1).mean()
            X_out['rolling_mean_30d'] = y_shift.rolling(window=30, min_periods=1).mean()
            X_out['rolling_std_7d'] = y_shift.rolling(window=7, min_periods=1).std()
            X_out['rolling_min_7d'] = y_shift.rolling(window=7, min_periods=1).min()
            X_out['rolling_max_7d'] = y_shift.rolling(window=7, min_periods=1).max()
            X_out['expanding_mean'] = y_shift.expanding().mean()
            
        # 'n_facturas' solo está presente en el dataset de ventas generales (sin
        # 'producto'); se usa como señal para acotar a ESE dataset las features nuevas de
        # docs/auditoria/21_...md, que no deben tocar el modelo de demanda (comparten este
        # mismo transformer). Ver hallazgo: la codificación cíclica sin acotar degradó
        # demand.pkl (R2 0.899->0.883, MAE 5.56->5.82, RMSE 172.97->185.85) al reentrenar
        # sin querer ambos modelos con las mismas columnas nuevas.
        es_dataset_ventas = 'n_facturas' in X_out.columns

        # Ticket promedio del día (venta neta / facturas). Se trata como exógena
        # contemporánea (se rezaga abajo junto con las demás): se calcula de las mismas
        # transacciones del target, usarla sin rezago sería fuga de datos.
        if es_dataset_ventas and self.target_col in X_out.columns:
            X_out['ticket_promedio'] = np.where(
                X_out['n_facturas'] > 0, X_out[self.target_col] / X_out['n_facturas'], 0.0
            )

        # Variables extraídas de la fecha si es el índice de Pandas (ds)
        if isinstance(X_out.index, pd.DatetimeIndex):
            X_out['is_weekend'] = (X_out.index.dayofweek >= 5).astype(int)
            X_out['day_of_week'] = X_out.index.dayofweek
            X_out['month'] = X_out.index.month
            X_out['quarter'] = X_out.index.quarter
            X_out['is_month_start'] = X_out.index.is_month_start.astype(int)
            X_out['is_month_end'] = X_out.index.is_month_end.astype(int)
            if es_dataset_ventas:
                X_out['dow_sin'] = np.sin(2 * np.pi * X_out.index.dayofweek / 7)
                X_out['dow_cos'] = np.cos(2 * np.pi * X_out.index.dayofweek / 7)
                X_out['month_sin'] = np.sin(2 * np.pi * X_out.index.month / 12)
                X_out['month_cos'] = np.cos(2 * np.pi * X_out.index.month / 12)
                # Feriados móviles solo para ventas (alcance aprobado, docs/auditoria/21_...md);
                # demanda conserva el cálculo original de solo fecha fija sin cambios.
                feriados_moviles_por_anio = {
                    anio: _feriados_movibles_ecuador(anio) for anio in X_out.index.year.unique()
                }
                X_out['es_feriado'] = [
                    1 if (d.month, d.day) in FERIADOS_ECUADOR_FECHA_FIJA
                    or (d.month, d.day) in feriados_moviles_por_anio[d.year] else 0
                    for d in X_out.index
                ]
            else:
                X_out['es_feriado'] = [
                    1 if (d.month, d.day) in FERIADOS_ECUADOR_FECHA_FIJA else 0 for d in X_out.index
                ]

        # Rezagar 1 día las exógenas contemporáneas (evita fuga de datos: ver constante arriba).
        for col in COLUMNAS_EXOGENAS_CONTEMPORANEAS:
            if col in X_out.columns:
                X_out[f'{col}_prev'] = X_out[col].shift(1)
                X_out.drop(columns=[col], inplace=True)

        # Imputar los NaN resultantes del shift/rolling con 0, NUNCA con bfill(): rellenar
        # hacia atrás usa valores FUTUROS para las primeras filas de cada serie, lo cual es
        # fuga de datos real (H-06, docs/auditoria/11_auditoria_tecnica_modelos_ml.md). En el
        # dataset de demanda (multi-producto, ordenado por fecha) un bfill global además podía
        # cruzar filas de OTRO producto. fillna(0) es conservador: las primeras filas de cada
        # serie quedan con lags/rolling en 0 en vez de con información que el modelo no tendría
        # disponible en producción.
        X_out = X_out.fillna(0)

        return X_out

def build_preprocessing_pipeline(target_col='y_sales_net') -> Pipeline:
    """
    Construye y devuelve un Pipeline de Scikit-Learn que agrupa 
    los pasos de feature engineering de series de tiempo más el escalado numérico.
    """
    pipeline = Pipeline([
        ('ts_features', TimeSeriesLagsTransformer(target_col=target_col, lags=(1, 7, 14, 30, 90))),
    ])
    return pipeline

def select_features_and_target(df: pd.DataFrame, target_col='y_sales_net'):
    """
    Divide el DataFrame en matriz X (predictoras) y vector Y (objetivo)
    """
    # Excluimos variables a usar netamente como Target directo.
    # El preprocesador ya generó the 'lags' dentro de la lógica.
    drop_cols = [target_col, 'y_quantity', 'sucursal', 'nombre', 'producto', 'ds']
    actual_drops = [c for c in drop_cols if c in df.columns]
    
    Y = df[target_col]
    X = df.drop(columns=actual_drops)
    
    return X, Y
