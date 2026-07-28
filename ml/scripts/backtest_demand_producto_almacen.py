# ml/scripts/backtest_demand_producto_almacen.py
"""Backtest del modelo de demanda REDISEÑADO (Fase 2, grano producto×almacén) --
contraparte de `backtest_demand_por_sku.py` (línea base, Fase 0) para poder comparar
manzanas con manzanas: mismo tipo de reporte (MAE/RMSE por decil de volumen histórico),
pero sobre `fetch_demand_by_product_warehouse` en vez de la serie global apilada.

Uso: desde ml/, con las mismas env vars PG_* que usa el entrenamiento real y
`ML_MODELS_DIR` apuntando al artefacto a evaluar.
"""
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.make_dataset import SalesTimeSerieExtractor, DEMANDA_MIN_MESES_VENTA
from src.features.build_features import build_preprocessing_pipeline, select_features_and_target

VENTANA_ENTRENAMIENTO_VENTAS_ANIOS = 3
import os
MODELS_DIR = Path(os.getenv("ML_MODELS_DIR", str(Path(__file__).resolve().parent.parent / "models")))
MODEL_PATH = MODELS_DIR / "demand.pkl"


def main() -> None:
    extractor = SalesTimeSerieExtractor()
    df_raw = extractor.fetch_demand_by_product_warehouse()
    print(f"Filas crudas (fecha, producto, almacén): {len(df_raw)}")

    fecha_corte = df_raw.index.max() - pd.DateOffset(years=VENTANA_ENTRENAMIENTO_VENTAS_ANIOS)
    df_raw = df_raw.loc[df_raw.index >= fecha_corte]

    n_combos_totales = df_raw.groupby(["producto", "almacen"]).ngroups
    meses_activos = (
        df_raw.reset_index()[["ds", "producto", "almacen"]]
        .assign(anio_mes=lambda d: d["ds"].dt.to_period("M"))
        .groupby(["producto", "almacen"])["anio_mes"].nunique()
        .rename("n_meses_activos")
        .reset_index()
    )
    combos_elegibles = meses_activos.loc[meses_activos["n_meses_activos"] >= DEMANDA_MIN_MESES_VENTA, ["producto", "almacen"]]
    df_raw = df_raw.reset_index().merge(combos_elegibles, on=["producto", "almacen"], how="inner").set_index("ds")
    print(f"Combinaciones elegibles (>= {DEMANDA_MIN_MESES_VENTA} meses activos): {len(combos_elegibles)} de {n_combos_totales}")

    pipeline = build_preprocessing_pipeline(target_col="y_quantity")
    df_features = pipeline.fit_transform(df_raw)

    train_size = int(len(df_features) * 0.8)
    df_train = df_features.iloc[:train_size]
    df_test = df_features.iloc[train_size:]
    print(f"Filas train: {len(df_train)} | Filas test (hold-out 20%): {len(df_test)}")
    print(f"Corte cronológico train/test: {df_test.index.min().date()}")

    X_train, y_train = select_features_and_target(df_train, "y_quantity")
    X_test, y_test = select_features_and_target(df_test, "y_quantity")

    model = joblib.load(MODEL_PATH)
    meta = json.loads((MODEL_PATH.with_suffix("").with_suffix(".meta.json")).read_text(encoding="utf-8"))
    features = meta["features"]
    faltantes = [f for f in features if f not in X_test.columns]
    if faltantes:
        raise RuntimeError(f"Features del contrato ausentes en el dataset reconstruido: {faltantes}")
    X_test_model = X_test[features]

    y_pred = np.clip(model.predict(X_test_model), 0, None)

    r2_global = r2_score(y_test, y_pred)
    mae_global = mean_absolute_error(y_test, y_pred)
    rmse_global = mean_squared_error(y_test, y_pred) ** 0.5
    print("\n=== MÉTRICA GLOBAL (modelo producto×almacén, solo combinaciones elegibles) ===")
    print(f"R2={r2_global:.4f}  MAE={mae_global:.4f}  RMSE={rmse_global:.4f}  n={len(y_test)}")

    resultado = pd.DataFrame({
        "producto": df_test["producto"].values,
        "almacen": df_test["almacen"].values,
        "y_real": y_test.values,
        "y_pred": y_pred,
    })
    resultado["error_abs"] = (resultado["y_real"] - resultado["y_pred"]).abs()
    resultado["error_cuad"] = (resultado["y_real"] - resultado["y_pred"]) ** 2

    volumen_por_combo = (
        df_train.groupby(["producto", "almacen"])["y_quantity"].sum().rename("volumen_train_total")
    )
    resultado = resultado.merge(volumen_por_combo, on=["producto", "almacen"], how="left")
    resultado["volumen_train_total"] = resultado["volumen_train_total"].fillna(0)

    try:
        resultado["decil_volumen"] = pd.qcut(resultado["volumen_train_total"], 10, labels=False, duplicates="drop")
    except ValueError:
        resultado["decil_volumen"] = 0

    print("\n=== MAE / RMSE por decil de volumen histórico de la combinación (0=más bajo, 9=más alto) ===")
    por_decil = resultado.groupby("decil_volumen").agg(
        n_filas=("error_abs", "size"),
        n_combos=("producto", "nunique"),
        volumen_medio=("volumen_train_total", "mean"),
        mae=("error_abs", "mean"),
        rmse=("error_cuad", lambda s: float(np.sqrt(s.mean()))),
    )
    print(por_decil.to_string(float_format=lambda x: f"{x:,.2f}"))


if __name__ == "__main__":
    main()
