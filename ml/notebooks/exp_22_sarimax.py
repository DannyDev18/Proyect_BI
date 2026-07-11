# ml/notebooks/exp_22_sarimax.py
"""Fase 3.3 del plan docs/auditoria/22_plan_mejora_modelo_ventas.md: SARIMAX como
referencia de series de tiempo clasica (expectativa baja, se documenta igual).

Comparacion JUSTA contra los arboles: los arboles se evaluan one-step-ahead (X_test
contiene los lags REALES del holdout), asi que SARIMAX tambien se evalua one-step-ahead:
se ajusta en el train, se extiende con los datos observados del test (refit=False) y se
toman las predicciones a un paso (dynamic=False). Un forecast dinamico de 199 pasos seria
una tarea mas dura y sesgaria la comparacion en contra de SARIMAX.

statsmodels NO esta en ml/requirements.txt (experimento de referencia, no dependencia del
pipeline): instalar ad-hoc en la corrida.
Ejecutar: docker compose run --rm ml sh -c "pip install -q statsmodels && python notebooks/exp_22_sarimax.py"
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from statsmodels.tsa.statespace.sarimax import SARIMAX

from src.data.make_dataset import SalesTimeSerieExtractor
from src.training.model_selector import evaluate_reg

VENTANA_ANIOS = 3

# Ordenes candidatos: estacionalidad semanal s=7 (la senal dominante segun la Fase 1:
# day_of_week concentra la importancia). Target en log1p (misma asimetria que los arboles).
ORDENES = [
    ((1, 0, 1), (1, 1, 1, 7)),
    ((2, 0, 2), (1, 1, 1, 7)),
    ((1, 1, 1), (0, 1, 1, 7)),
]


def main():
    warnings.filterwarnings("ignore")
    extractor = SalesTimeSerieExtractor()
    df = extractor.fetch_daily_sales()[["y_sales_net"]]
    # SARIMAX exige frecuencia regular: reindexar a diario, dias sin venta = 0 (mismo
    # criterio que el serving del backend: resample("D").sum().fillna(0)).
    df = df.resample("D").sum().fillna(0.0)
    fecha_corte = df.index.max() - pd.DateOffset(years=VENTANA_ANIOS)
    df = df.loc[df.index >= fecha_corte]
    # El split 80/20 del pipeline de arboles se hace sobre dias CON venta (992 filas);
    # aqui se usa la misma fecha de corte del test para que el holdout cubra el mismo periodo.
    train_size = int(len(df) * 0.8)
    y = np.log1p(df["y_sales_net"])
    y_train, y_test = y.iloc[:train_size], y.iloc[train_size:]
    y_test_real = df["y_sales_net"].iloc[train_size:]
    print(f"Train {len(y_train)} dias ({y_train.index.min().date()} -> {y_train.index.max().date()}) | "
          f"Test {len(y_test)} dias ({y_test.index.min().date()} -> {y_test.index.max().date()})")

    for order, seasonal in ORDENES:
        try:
            res = SARIMAX(y_train, order=order, seasonal_order=seasonal,
                          enforce_stationarity=False, enforce_invertibility=False).fit(disp=False)
            res_ext = res.append(y_test, refit=False)
            pred_log = res_ext.get_prediction(start=y_test.index[0], end=y_test.index[-1], dynamic=False)
            y_pred = np.maximum(0, np.expm1(pred_log.predicted_mean))
            m = evaluate_reg(y_test_real, y_pred)
            print(f"SARIMAX{order}x{seasonal}: R2={m['R2']:+.4f}  MAE={m['MAE']:.2f}  RMSE={m['RMSE']:.2f}")
        except Exception as e:
            print(f"SARIMAX{order}x{seasonal}: FALLO ({e})")


if __name__ == "__main__":
    main()
