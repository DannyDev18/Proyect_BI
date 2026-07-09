# backend/app/ml/preprocessing.py
"""Feature engineering para serving (inferencia en vivo).

Copiado/internalizado desde `ml/src/features/build_features.py` (el pipeline de
ENTRENAMIENTO, fuera de `backend/`). Se internaliza a propósito: el backend de
serving no debe importar código fuente del paquete de entrenamiento (acoplamiento
cross-boundary vía volumen Docker montado). El trade-off es que ambas copias
pueden desincronizarse si se cambia el feature engineering de entrenamiento sin
actualizar esta -- es un riesgo real y documentado, no un descuido: si cambia
`ml/src/features/build_features.py`, hay que revisar si este archivo necesita el
mismo cambio, porque `model.feature_names_in_` debe coincidir exactamente con lo
que este módulo genera (ver `app/ml/inference.py`).
"""
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.pipeline import Pipeline

# Feriados nacionales de fecha fija en Ecuador (Dim_Fecha.es_feriado nunca se puebla en el
# EDW). Los móviles (Carnaval, Viernes Santo) quedan fuera por simplicidad.
FERIADOS_ECUADOR_FECHA_FIJA = {(1, 1), (5, 1), (5, 24), (7, 24), (8, 10), (10, 9), (11, 2), (11, 3), (12, 25)}

# Columnas exógenas que se calculan del MISMO día que el target (derivadas de las mismas
# transacciones). Usarlas tal cual sería fuga de datos; se rezagan 1 día.
COLUMNAS_EXOGENAS_CONTEMPORANEAS = ['n_clientes', 'n_facturas', 'pct_descuento_prom']


class TimeSeriesLagsTransformer(BaseEstimator, TransformerMixin):
    """Genera lags y variables temporales/calendario para modelos de tabla (RF/XGB/etc.)
    que no tienen memoria temporal nativa."""

    def __init__(self, target_col='y_sales_net', lags=(1, 7, 30)):
        self.target_col = target_col
        self.lags = lags

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        X_out = X.copy()

        if 'producto' in X_out.columns:
            for lag in self.lags:
                X_out[f'lag_{lag}_{self.target_col}'] = X_out.groupby('producto')[self.target_col].shift(lag)
            gb = X_out.groupby('producto')[self.target_col]
            X_out['rolling_mean_7d'] = gb.transform(lambda x: x.shift(1).rolling(window=7, min_periods=1).mean())
            X_out['rolling_mean_30d'] = gb.transform(lambda x: x.shift(1).rolling(window=30, min_periods=1).mean())
            X_out['rolling_std_7d'] = gb.transform(lambda x: x.shift(1).rolling(window=7, min_periods=1).std())
            X_out['rolling_min_7d'] = gb.transform(lambda x: x.shift(1).rolling(window=7, min_periods=1).min())
            X_out['rolling_max_7d'] = gb.transform(lambda x: x.shift(1).rolling(window=7, min_periods=1).max())
            X_out['expanding_mean'] = gb.transform(lambda x: x.shift(1).expanding().mean())
        else:
            for lag in self.lags:
                X_out[f'lag_{lag}_{self.target_col}'] = X_out[self.target_col].shift(lag)

            y_shift = X_out[self.target_col].shift(1)
            X_out['rolling_mean_7d'] = y_shift.rolling(window=7, min_periods=1).mean()
            X_out['rolling_mean_30d'] = y_shift.rolling(window=30, min_periods=1).mean()
            X_out['rolling_std_7d'] = y_shift.rolling(window=7, min_periods=1).std()
            X_out['rolling_min_7d'] = y_shift.rolling(window=7, min_periods=1).min()
            X_out['rolling_max_7d'] = y_shift.rolling(window=7, min_periods=1).max()
            X_out['expanding_mean'] = y_shift.expanding().mean()

        if isinstance(X_out.index, pd.DatetimeIndex):
            X_out['is_weekend'] = (X_out.index.dayofweek >= 5).astype(int)
            X_out['day_of_week'] = X_out.index.dayofweek
            X_out['month'] = X_out.index.month
            X_out['quarter'] = X_out.index.quarter
            X_out['is_month_start'] = X_out.index.is_month_start.astype(int)
            X_out['is_month_end'] = X_out.index.is_month_end.astype(int)
            X_out['es_feriado'] = [
                1 if (d.month, d.day) in FERIADOS_ECUADOR_FECHA_FIJA else 0 for d in X_out.index
            ]

        for col in COLUMNAS_EXOGENAS_CONTEMPORANEAS:
            if col in X_out.columns:
                X_out[f'{col}_prev'] = X_out[col].shift(1)
                X_out.drop(columns=[col], inplace=True)

        X_out = X_out.bfill().fillna(0)
        return X_out


def build_preprocessing_pipeline(target_col='y_sales_net') -> Pipeline:
    """Pipeline de sklearn (Strategy: cada Transformer es intercambiable) con los mismos
    lags usados en entrenamiento -- deben coincidir para que `feature_names_in_` del
    modelo encuentre todas sus columnas en tiempo de inferencia."""
    return Pipeline([
        ('ts_features', TimeSeriesLagsTransformer(target_col=target_col, lags=(1, 7, 14, 30, 90))),
    ])


def select_features_and_target(df: pd.DataFrame, target_col='y_sales_net'):
    """Separa el DataFrame en matriz X (predictoras) y vector Y (objetivo)."""
    drop_cols = [target_col, 'y_quantity', 'sucursal', 'nombre', 'producto', 'ds']
    actual_drops = [c for c in drop_cols if c in df.columns]
    Y = df[target_col]
    X = df.drop(columns=actual_drops)
    return X, Y
