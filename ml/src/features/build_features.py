# ml/src/preprocessor.py
import pandas as pd
import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

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
            
        # Variables extraídas de la fecha si es el índice de Pandas (ds)
        if isinstance(X_out.index, pd.DatetimeIndex):
            X_out['is_weekend'] = (X_out.index.dayofweek >= 5).astype(int)
            X_out['day_of_week'] = X_out.index.dayofweek
            X_out['month'] = X_out.index.month
            X_out['quarter'] = X_out.index.quarter
            X_out['is_month_start'] = X_out.index.is_month_start.astype(int)
            X_out['is_month_end'] = X_out.index.is_month_end.astype(int)

        # Imputar los NaN resultantes del shift manteniendo soporte para groupbys temporales
        X_out = X_out.bfill().fillna(0)
            
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
