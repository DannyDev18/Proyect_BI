# backend/app/ml/forecasting.py
"""Simulación walk-forward compartida por los dos consumidores del modelo de ventas:
`PredictionService.get_sales_forecast_weekly` (Gerencia, horizonte fijo de 14 días) y
`GoalMLService` (integración Metas y Comisiones -- horizonte variable: días restantes
del mes en curso, para proyectar el cierre de un vendedor/sucursal). Antes este loop
vivía duplicado inline en `prediction_service.py`; se extrae aquí para no reimplementarlo
en la integración de metas (instrucción explícita: no duplicar lógica)."""
from typing import Callable

import pandas as pd

from app.ml.model_loader import ModelLoader
from app.ml.preprocessing import build_preprocessing_pipeline, select_features_and_target

PredictFn = Callable[[ModelLoader, pd.DataFrame], pd.Series]


def walk_forward_forecast(
    loader: ModelLoader,
    df_hist_raw: pd.DataFrame,
    target_col: str,
    dias: int,
    predict_fn: PredictFn,
) -> list[tuple[pd.Timestamp, float]]:
    """Cada predicción se re-inyecta como "historia" para poder generar los
    lags/rolling del día siguiente. `df_hist_raw` debe venir indexado por fecha
    (DatetimeIndex), resampleado a diario y sin huecos -- igual precondición que
    `PredictionService.get_sales_forecast_weekly` ya exigía."""
    if dias <= 0 or df_hist_raw.empty:
        return []
    pipeline = build_preprocessing_pipeline(target_col)
    df_sim = df_hist_raw.copy()
    generated: list[tuple[pd.Timestamp, float]] = []

    for _ in range(dias):
        next_day = df_sim.index[-1] + pd.Timedelta(days=1)
        df_sim.loc[next_day] = 0.0

        df_feat = pipeline.fit_transform(df_sim.copy())
        X, _ = select_features_and_target(df_feat, target_col)
        X_live = X.iloc[[-1]]

        y_p = max(0.0, float(predict_fn(loader, X_live).iloc[0]))
        df_sim.loc[next_day, target_col] = y_p
        generated.append((next_day, y_p))

    return generated
