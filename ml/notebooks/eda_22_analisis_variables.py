# ml/notebooks/eda_22_analisis_variables.py
"""Fase 1 del plan docs/auditoria/22_plan_mejora_modelo_ventas.md (puntos 1.1-1.3):
analisis de correlacion (Pearson + Spearman) de cada feature contra y_sales_net,
matriz de correlacion ENTRE features (multicolinealidad) y permutation importance
sobre el modelo sales.pkl vigente, evaluada en el holdout cronologico.

Script de EDA aislado: NO modifica ml/main.py ni reentrena nada. Reproduce fielmente
el pipeline real de entrenamiento (fetch_daily_sales -> build_preprocessing_pipeline
-> ventana 3 anios -> split cronologico 80/20) para que el analisis corresponda a lo
que el modelo realmente ve.

Ejecutar desde la raiz del repo:
    docker compose run --rm ml python notebooks/eda_22_analisis_variables.py
"""
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr
from sklearn.inspection import permutation_importance

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # /app dentro del contenedor

from src.data.make_dataset import SalesTimeSerieExtractor
from src.features.build_features import build_preprocessing_pipeline, select_features_and_target

VENTANA_ANIOS = 3  # misma ventana que ml/main.py::VENTANA_ENTRENAMIENTO_VENTAS_ANIOS
UMBRAL_MULTICOLINEALIDAD = 0.90
OUT_DIR = Path(__file__).resolve().parent / "output_22"


def cargar_dataset():
    extractor = SalesTimeSerieExtractor()
    df_raw = extractor.fetch_daily_sales()
    pipeline = build_preprocessing_pipeline()
    df_features = pipeline.fit_transform(df_raw)
    fecha_corte = df_features.index.max() - pd.DateOffset(years=VENTANA_ANIOS)
    df_features = df_features.loc[df_features.index >= fecha_corte]
    train_size = int(len(df_features) * 0.8)
    return df_features.iloc[:train_size], df_features.iloc[train_size:]


def correlaciones_vs_target(X: pd.DataFrame, y: pd.Series) -> pd.DataFrame:
    filas = []
    for col in X.columns:
        x = X[col].astype(float)
        if x.nunique() <= 1:
            filas.append({"feature": col, "pearson": np.nan, "spearman": np.nan})
            continue
        filas.append({
            "feature": col,
            "pearson": pearsonr(x, y)[0],
            "spearman": spearmanr(x, y)[0],
        })
    return pd.DataFrame(filas).set_index("feature")


def pares_multicolineales(X: pd.DataFrame, umbral: float) -> pd.DataFrame:
    corr = X.corr(method="pearson")
    pares = []
    cols = corr.columns
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            r = corr.iloc[i, j]
            if abs(r) >= umbral:
                pares.append({"feature_a": cols[i], "feature_b": cols[j], "pearson": r})
    return pd.DataFrame(pares).sort_values("pearson", key=abs, ascending=False) if pares else pd.DataFrame()


def importancia_permutacion(X_test: pd.DataFrame, y_test: pd.Series) -> pd.DataFrame:
    modelo = joblib.load(Path(__file__).resolve().parents[1] / "models" / "sales.pkl")
    meta = json.loads((Path(__file__).resolve().parents[1] / "models" / "sales.meta.json").read_text())
    features = meta["features"]
    X_eval = X_test[features]
    # scoring r2 en escala USD real: el artefacto es TransformedTargetRegressor autocontenido (H-01)
    result = permutation_importance(
        modelo, X_eval, y_test, n_repeats=15, random_state=42, scoring="r2", n_jobs=-1
    )
    return pd.DataFrame({
        "feature": features,
        "importancia_media": result.importances_mean,
        "importancia_std": result.importances_std,
    }).sort_values("importancia_media", ascending=False).set_index("feature")


def main():
    OUT_DIR.mkdir(exist_ok=True)
    df_train, df_test = cargar_dataset()
    X_train, y_train = select_features_and_target(df_train, "y_sales_net")
    X_test, y_test = select_features_and_target(df_test, "y_sales_net")
    print(f"Train: {len(X_train)} filas | Test: {len(X_test)} filas | Features: {len(X_train.columns)}")
    print(f"Rango train: {df_train.index.min().date()} -> {df_train.index.max().date()}")
    print(f"Rango test : {df_test.index.min().date()} -> {df_test.index.max().date()}\n")

    # 1.1 Correlaciones contra el target (sobre el TRAIN, para no mirar el holdout)
    corr = correlaciones_vs_target(X_train, y_train)
    corr.to_csv(OUT_DIR / "correlaciones_vs_target.csv")
    print("== Correlacion de cada feature vs y_sales_net (train) ==")
    print(corr.sort_values("spearman", key=abs, ascending=False).round(4).to_string())

    # 1.2 Multicolinealidad entre features
    pares = pares_multicolineales(X_train, UMBRAL_MULTICOLINEALIDAD)
    pares.to_csv(OUT_DIR / "pares_multicolineales.csv", index=False)
    print(f"\n== Pares de features con |r| >= {UMBRAL_MULTICOLINEALIDAD} ==")
    print(pares.round(4).to_string(index=False) if not pares.empty else "(ninguno)")

    # 1.3 Permutation importance sobre sales.pkl en el holdout
    imp = importancia_permutacion(X_test, y_test)
    imp.to_csv(OUT_DIR / "permutation_importance.csv")
    print("\n== Permutation importance (sales.pkl vigente, holdout, scoring=r2, n_repeats=15) ==")
    print(imp.round(5).to_string())


if __name__ == "__main__":
    main()
