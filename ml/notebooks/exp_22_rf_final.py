# Barrido final de n_estimators del RF default (ganador provisional de Fases 1/3),
# protocolo Fase 2: 3 semillas, mismo split. Ver docs/auditoria/22_plan_mejora_modelo_ventas.md.
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sklearn.compose import TransformedTargetRegressor
from sklearn.ensemble import RandomForestRegressor
from src.data.make_dataset import SalesTimeSerieExtractor
from src.features.build_features import build_preprocessing_pipeline, select_features_and_target
from src.training.model_selector import evaluate_reg

extractor = SalesTimeSerieExtractor()
df = build_preprocessing_pipeline().fit_transform(extractor.fetch_daily_sales())
df = df.loc[df.index >= df.index.max() - pd.DateOffset(years=3)]
n = int(len(df) * 0.8)
X_train, y_train = select_features_and_target(df.iloc[:n], "y_sales_net")
X_test, y_test = select_features_and_target(df.iloc[n:], "y_sales_net")

for n_est in (100, 200, 300, 500, 800):
    r2s, maes, rmses = [], [], []
    for seed in (42, 7, 2026):
        m = TransformedTargetRegressor(
            regressor=RandomForestRegressor(n_estimators=n_est, random_state=seed, n_jobs=-1),
            func=np.log1p, inverse_func=np.expm1)
        m.fit(X_train, y_train)
        met = evaluate_reg(y_test, m.predict(X_test))
        r2s.append(met["R2"]); maes.append(met["MAE"]); rmses.append(met["RMSE"])
    print(f"n_estimators={n_est:4d}  R2={np.mean(r2s):+.4f}±{np.std(r2s):.4f}  "
          f"MAE={np.mean(maes):.2f}  RMSE={np.mean(rmses):.2f}")
