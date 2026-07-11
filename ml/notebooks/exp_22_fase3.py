# ml/notebooks/exp_22_fase3.py
"""Fase 3.1 y 3.2 del plan docs/auditoria/22_plan_mejora_modelo_ventas.md.

3.1 Busqueda profunda de hiperparametros (RandomizedSearchCV n_iter=25, vs n_iter=5 del
    model_selector actual) sobre los 5 algoritmos tabulares, con el protocolo de la Fase 2:
    3 corridas por algoritmo (random_state de la busqueda distinto en cada una), promedio
    +- desviacion de R2/MAE/RMSE en el holdout cronologico. Set de features = las 26 del
    baseline (resultado de la Fase 1: el set depurado y todos los candidatos nuevos
    empeoraron o fueron neutros -- ver exp_22_features.py).

3.2 Regresion por cuantiles (LightGBM objective='quantile', P10/P50/P90): metricas del P50
    + cobertura empirica del intervalo [P10, P90] en el holdout (nominal: 80%). El target
    para cuantiles se modela en escala REAL (no log1p): el cuantil es invariante a
    transformaciones monotonas en teoria, pero la perdida pinball que optimiza LightGBM no
    lo es -- optimizar el cuantil en log-espacio sesga el intervalo en USD.

Ejecutar: docker compose run --rm ml python notebooks/exp_22_fase3.py
"""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lightgbm as lgb
import xgboost as xgb
import catboost as cb
from sklearn.compose import TransformedTargetRegressor
from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor
from sklearn.model_selection import RandomizedSearchCV, TimeSeriesSplit

from src.data.make_dataset import SalesTimeSerieExtractor
from src.features.build_features import build_preprocessing_pipeline, select_features_and_target
from src.training.model_selector import evaluate_reg

VENTANA_ANIOS = 3
SEEDS = (42, 7, 2026)
N_ITER = 25

# Paralelismo: SOLO en el nivel del RandomizedSearchCV (n_jobs=-1); todos los estimadores
# van monohilo (n_jobs=1/thread_count=1). Dos capas de paralelismo a la vez (estimador -1 +
# search -1) sobresuscriben 32x32 hilos y la corrida tarda horas en vez de minutos (medido
# en esta misma fase); ademas es la config segura contra el deadlock anidado de
# model_selector.py (alli el interno era paralelo y el externo secuencial -- aqui al reves).
GRIDS = {
    "RandomForest": (lambda: RandomForestRegressor(n_jobs=1, random_state=42), {
        "n_estimators": [100, 200, 300, 500],
        "max_depth": [5, 10, 20, None],
        "min_samples_leaf": [1, 2, 5, 10],
        "max_features": ["sqrt", 0.5, 1.0],
    }, -1),
    "XGBoost": (lambda: xgb.XGBRegressor(objective="reg:squarederror", n_jobs=1, random_state=42), {
        "n_estimators": [100, 200, 300, 500],
        "learning_rate": [0.005, 0.01, 0.03, 0.05, 0.1],
        "max_depth": [3, 4, 5, 7],
        "subsample": [0.7, 0.8, 1.0],
        "colsample_bytree": [0.7, 0.9, 1.0],
        "reg_lambda": [0.5, 1.0, 5.0],
    }, -1),
    "LightGBM": (lambda: lgb.LGBMRegressor(n_jobs=1, random_state=42, verbose=-1), {
        "n_estimators": [100, 200, 300, 500],
        "learning_rate": [0.005, 0.01, 0.03, 0.05, 0.1],
        "num_leaves": [15, 31, 50, 100],
        "max_depth": [-1, 5, 10],
        "min_child_samples": [10, 20, 40],
        "subsample": [0.7, 0.9, 1.0],
    }, -1),
    "CatBoost": (lambda: cb.CatBoostRegressor(verbose=0, thread_count=1, random_state=42), {
        "iterations": [100, 200, 300, 500],
        "learning_rate": [0.005, 0.01, 0.03, 0.05, 0.1],
        "depth": [4, 6, 8],
        "l2_leaf_reg": [1, 3, 9],
    }, -1),
    "HistGradientBoosting": (lambda: HistGradientBoostingRegressor(random_state=42), {
        "max_iter": [100, 200, 300, 500],
        "learning_rate": [0.005, 0.01, 0.03, 0.05, 0.1],
        "max_depth": [5, 10, None],
        "max_leaf_nodes": [15, 31, 63],
        "l2_regularization": [0.0, 0.1, 1.0],
    }, -1),
}


def cargar():
    extractor = SalesTimeSerieExtractor()
    df_raw = extractor.fetch_daily_sales()
    pipeline = build_preprocessing_pipeline()
    df = pipeline.fit_transform(df_raw)
    fecha_corte = df.index.max() - pd.DateOffset(years=VENTANA_ANIOS)
    df = df.loc[df.index >= fecha_corte]
    train_size = int(len(df) * 0.8)
    df_train, df_test = df.iloc[:train_size], df.iloc[train_size:]
    X_train, y_train = select_features_and_target(df_train, "y_sales_net")
    X_test, y_test = select_features_and_target(df_test, "y_sales_net")
    return X_train, y_train, X_test, y_test


def fase31(X_train, y_train, X_test, y_test):
    print("== Fase 3.1: busqueda profunda de hiperparametros (n_iter=25, 3 semillas) ==")
    y_train_log = np.log1p(y_train)
    tscv = TimeSeriesSplit(n_splits=3)
    filas = []
    for nombre, (factory, grid, search_jobs) in GRIDS.items():
        r2s, maes, rmses, params_ganadores = [], [], [], []
        t0 = time.time()
        for seed in SEEDS:
            search = RandomizedSearchCV(
                estimator=factory(), param_distributions=grid, n_iter=N_ITER, cv=tscv,
                scoring="neg_root_mean_squared_error", random_state=seed, n_jobs=search_jobs,
            )
            search.fit(X_train, y_train_log)
            modelo = TransformedTargetRegressor(
                regressor=type(search.best_estimator_)(**search.best_estimator_.get_params()),
                func=np.log1p, inverse_func=np.expm1,
            )
            modelo.fit(X_train, y_train)
            m = evaluate_reg(y_test, modelo.predict(X_test))
            r2s.append(m["R2"]); maes.append(m["MAE"]); rmses.append(m["RMSE"])
            params_ganadores.append(search.best_params_)
        print(f"{nombre:22s} R2={np.mean(r2s):+.4f}±{np.std(r2s):.4f}  MAE={np.mean(maes):8.2f}±{np.std(maes):6.2f}  "
              f"RMSE={np.mean(rmses):8.2f}±{np.std(rmses):6.2f}  [{time.time()-t0:5.1f}s]")
        for seed, p in zip(SEEDS, params_ganadores):
            print(f"    seed {seed}: {p}")
        filas.append({"algoritmo": nombre, "r2": np.mean(r2s), "r2_std": np.std(r2s),
                      "mae": np.mean(maes), "rmse": np.mean(rmses),
                      "params_por_seed": params_ganadores})
    return filas


def fase32(X_train, y_train, X_test, y_test):
    print("\n== Fase 3.2: regresion por cuantiles LightGBM (P10/P50/P90, escala real) ==")
    filas = []
    for seed in SEEDS:
        modelos = {}
        for alpha in (0.10, 0.50, 0.90):
            m = lgb.LGBMRegressor(
                objective="quantile", alpha=alpha, n_estimators=300, learning_rate=0.05,
                num_leaves=31, n_jobs=-1, random_state=seed, verbose=-1,
            )
            m.fit(X_train, y_train)
            modelos[alpha] = m
        p10 = np.maximum(0, modelos[0.10].predict(X_test))
        p50 = np.maximum(0, modelos[0.50].predict(X_test))
        p90 = np.maximum(0, modelos[0.90].predict(X_test))
        met = evaluate_reg(y_test, p50)
        cobertura = float(np.mean((y_test.values >= p10) & (y_test.values <= p90)))
        ancho = float(np.mean(p90 - p10))
        filas.append({**met, "cobertura_p10_p90": cobertura, "ancho_medio_usd": ancho})
        print(f"  seed {seed}: P50 R2={met['R2']:+.4f} MAE={met['MAE']:.2f} RMSE={met['RMSE']:.2f} | "
              f"cobertura[P10,P90]={cobertura:.1%} (nominal 80%) ancho medio=${ancho:,.0f}")
    df = pd.DataFrame(filas)
    print(f"  PROMEDIO: P50 R2={df['R2'].mean():+.4f}±{df['R2'].std(ddof=0):.4f} MAE={df['MAE'].mean():.2f} "
          f"RMSE={df['RMSE'].mean():.2f} cobertura={df['cobertura_p10_p90'].mean():.1%}")
    return filas


def main():
    X_train, y_train, X_test, y_test = cargar()
    print(f"Train {len(X_train)} filas | Test {len(X_test)} filas | {X_train.shape[1]} features (baseline Fase 1)\n")
    filas31 = fase31(X_train, y_train, X_test, y_test)
    filas32 = fase32(X_train, y_train, X_test, y_test)
    out = Path(__file__).resolve().parent / "output_22"
    out.mkdir(exist_ok=True)
    pd.DataFrame(filas31).to_csv(out / "fase31_hyperparam_search.csv", index=False)
    pd.DataFrame(filas32).to_csv(out / "fase32_quantile.csv", index=False)


if __name__ == "__main__":
    main()
