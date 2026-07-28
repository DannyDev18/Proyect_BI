# ml/scripts/backtest_demand_por_sku.py
"""Backtest de línea base (Fase 0, docs/features/plan_mejora_pipeline_ml.md) del modelo de
demanda vigente (`demand.pkl`, entrenado como serie global apilada de todos los SKU).

Reproduce EXACTAMENTE el flujo de `ml/main.py::train_demand_forecasting` (mismo fetch,
mismo pipeline de features, misma ventana de 3 años, mismo split cronológico 80/20) para
poder comparar manzanas con manzanas, pero conserva la columna `producto` (descartada por
`select_features_and_target` antes de entrenar) solo para AGRUPAR el error de predicción
por SKU y por decil de volumen -- nunca se la pasa al modelo. Cuantifica el hallazgo D-1
del plan: el R2 global (0.876) esconde un error real muy distinto entre SKUs de bajo y
alto volumen (RMSE=191 vs MAE=6.2 en el `.meta.json` ya sugiere esa brecha).

Uso: desde ml/, con las mismas env vars PG_* que usa el entrenamiento real.
    PG_HOST=localhost PG_PORT=5433 PG_USER=etl_user PG_PASSWORD=... python scripts/backtest_demand_por_sku.py
"""
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.make_dataset import SalesTimeSerieExtractor
from src.features.build_features import build_preprocessing_pipeline, select_features_and_target

VENTANA_ENTRENAMIENTO_VENTAS_ANIOS = 3
MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "demand.pkl"


def main() -> None:
    extractor = SalesTimeSerieExtractor()
    df_raw = extractor.fetch_sales_by_dimension(dimension="producto")
    print(f"Filas crudas (fecha, producto): {len(df_raw)}")

    pipeline = build_preprocessing_pipeline(target_col="y_quantity")
    df_features = pipeline.fit_transform(df_raw)

    fecha_corte = df_features.index.max() - pd.DateOffset(years=VENTANA_ENTRENAMIENTO_VENTAS_ANIOS)
    df_features = df_features.loc[df_features.index >= fecha_corte]

    train_size = int(len(df_features) * 0.8)
    df_train = df_features.iloc[:train_size]
    df_test = df_features.iloc[train_size:]
    print(f"Ventana entrenamiento: {df_features.index.min().date()} -> {df_features.index.max().date()}")
    print(f"Filas train: {len(df_train)} | Filas test (hold-out 20%): {len(df_test)}")
    print(f"Corte cronológico train/test: {df_test.index.min().date()}")

    X_train, y_train = select_features_and_target(df_train, "y_quantity")
    X_test, y_test = select_features_and_target(df_test, "y_quantity")

    model = joblib.load(MODEL_PATH)
    meta = json.loads((MODEL_PATH.with_suffix("").with_suffix(".meta.json")).read_text(encoding="utf-8"))
    features = meta["features"]
    faltantes = [f for f in features if f not in X_test.columns]
    if faltantes:
        raise RuntimeError(f"El dataset reconstruido no tiene las features del contrato vigente: {faltantes}")
    X_test_model = X_test[features]

    y_pred = model.predict(X_test_model)
    y_pred = np.clip(y_pred, 0, None)  # la cantidad no puede ser negativa

    r2_global = r2_score(y_test, y_pred)
    mae_global = mean_absolute_error(y_test, y_pred)
    rmse_global = mean_squared_error(y_test, y_pred) ** 0.5
    print("\n=== MÉTRICA GLOBAL (la que hoy se reporta en demand.meta.json) ===")
    print(f"R2={r2_global:.4f}  MAE={mae_global:.4f}  RMSE={rmse_global:.4f}  n={len(y_test)}")

    resultado = pd.DataFrame({
        "producto": df_test["producto"].values,
        "y_real": y_test.values,
        "y_pred": y_pred,
    })
    resultado["error_abs"] = (resultado["y_real"] - resultado["y_pred"]).abs()
    resultado["error_cuad"] = (resultado["y_real"] - resultado["y_pred"]) ** 2

    # Volumen histórico de cada SKU (para decil), calculado sobre TODO el dataset de train
    # (lo que el modelo "vio"), no sobre el test, para no filtrar información del hold-out
    # hacia la asignación de deciles.
    volumen_por_sku = df_train.groupby("producto")["y_quantity"].sum().rename("volumen_train_total")
    resultado = resultado.merge(volumen_por_sku, on="producto", how="left")
    resultado["volumen_train_total"] = resultado["volumen_train_total"].fillna(0)

    try:
        resultado["decil_volumen"] = pd.qcut(
            resultado["volumen_train_total"], 10, labels=False, duplicates="drop"
        )
    except ValueError:
        resultado["decil_volumen"] = 0

    print("\n=== MAE / RMSE por decil de volumen histórico del SKU (0=más bajo, 9=más alto) ===")
    por_decil = resultado.groupby("decil_volumen").agg(
        n_filas=("error_abs", "size"),
        n_skus=("producto", "nunique"),
        volumen_medio=("volumen_train_total", "mean"),
        mae=("error_abs", "mean"),
        rmse=("error_cuad", lambda s: float(np.sqrt(s.mean()))),
    )
    print(por_decil.to_string(float_format=lambda x: f"{x:,.2f}"))

    print("\n=== Top 15 SKU con mayor error absoluto medio (mínimo 5 observaciones en test) ===")
    por_sku = resultado.groupby("producto").agg(
        n=("error_abs", "size"), mae=("error_abs", "mean"), volumen_train_total=("volumen_train_total", "first")
    )
    por_sku = por_sku[por_sku["n"] >= 5].sort_values("mae", ascending=False).head(15)
    print(por_sku.to_string(float_format=lambda x: f"{x:,.2f}"))

    n_skus_total = df_features["producto"].nunique()
    n_skus_test = resultado["producto"].nunique()
    print(f"\nSKUs distintos en toda la ventana de 3 años: {n_skus_total}")
    print(f"SKUs distintos en el hold-out de test: {n_skus_test}")

    # Intermitencia: fracción de combinaciones (producto, mes) con demanda cero, sobre el
    # dataset completo -- insumo para decidir si el grano producto×almacén (Fase 2) necesita
    # un modelo de dos etapas (clasificador de "hay salida" + regresor de cantidad).
    df_mes = df_features.reset_index().rename(columns={"index": "ds"})
    df_mes["anio_mes"] = df_mes["ds"].dt.to_period("M")
    agregado_mes = df_mes.groupby(["producto", "anio_mes"])["y_quantity"].sum().reset_index()
    pct_ceros = (agregado_mes["y_quantity"] == 0).mean()
    print(f"\n% de combinaciones (producto, mes) con demanda mensual = 0: {pct_ceros:.2%}")
    print(f"Total combinaciones (producto, mes) observadas: {len(agregado_mes)}")


if __name__ == "__main__":
    main()
