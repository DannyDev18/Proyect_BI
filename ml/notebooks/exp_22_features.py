# ml/notebooks/exp_22_features.py
"""Fase 1.4-1.5 del plan docs/auditoria/22_plan_mejora_modelo_ventas.md: evaluacion de
candidatos de features contra el baseline, con el protocolo de la Fase 2 (3 corridas por
configuracion, promedio +- desviacion; mismo split cronologico 80/20 y ventana de 3 anios).

Para aislar el efecto de las FEATURES (no del algoritmo), todas las configuraciones usan el
mismo estimador fijo: RandomForestRegressor (algoritmo ganador vigente) envuelto en
TransformedTargetRegressor(log1p/expm1), variando solo random_state entre corridas.

Configuraciones:
  A. baseline           -- las 26 features actuales (contrato sales v0.2.0)
  B. depurado           -- baseline menos features con importancia ~0/negativa y redundantes
                           (Fase 1.3: month, quarter, expanding_mean, rolling_mean_30d,
                           lag_14, lag_30, ticket_promedio_prev, n_facturas_prev)
  C. baseline+picos     -- flags de pico atipico construidos SOLO con historia (shift 1):
                           pico_prev (ayer fue pico por z-score robusto) y n_picos_7d
  D. baseline sin picos en TRAIN -- estrategia alternativa: excluir dias atipicos del
                           entrenamiento (holdout intacto, se evalua completo)
  E. baseline+compras   -- valor_compras_prev (fact_compras agregada al dia, rezagada 1 dia)
  F. baseline+devol     -- valor_devoluciones_prev (fact_devoluciones agregada, rezagada 1 dia)

Ejecutar: docker compose run --rm ml python notebooks/exp_22_features.py
"""
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

VENTANA_ANIOS = 3
SEEDS = (42, 7, 2026)
Z_ROBUSTO_UMBRAL = 3.5  # umbral clasico de outlier con z-score robusto (mediana/MAD)
VENTANA_Z = 28          # ventana movil para mediana/MAD del z robusto

# Fase 1.3 (eda_22_analisis_variables.py): importancia por permutacion <= 0 o redundancia
# (n_facturas_prev con n_clientes_prev r=0.989; quarter con month r=0.97).
FEATURES_A_REMOVER_DEPURADO = [
    "month", "quarter", "expanding_mean", "rolling_mean_30d",
    "lag_14_y_sales_net", "lag_30_y_sales_net", "ticket_promedio_prev", "n_facturas_prev",
]


def _sql_agregado_diario(engine, sql: str, col: str) -> pd.Series:
    df = pd.read_sql(sql, engine)
    df["ds"] = pd.to_datetime(df["ds"])
    return df.set_index("ds")[col]


def fetch_exogenas_candidatas(extractor: SalesTimeSerieExtractor) -> pd.DataFrame:
    """Agrega cada hecho POR SEPARADO al grano diario (patron de CTEs/agregados de la skill
    ml-training-pipeline: nunca JOIN directo entre hechos de grano distinto). Centinelas de
    producto/proveedor no aplican al agregado por dia (se suma la medida completa del hecho)."""
    compras = _sql_agregado_diario(extractor.engine, """
        SELECT df.fecha_completa AS ds, SUM(fc.costo_linea) AS valor_compras_dia
        FROM edw.fact_compras fc
        JOIN edw.dim_fecha df ON fc.fecha_sk = df.fecha_sk
        GROUP BY df.fecha_completa ORDER BY df.fecha_completa;
    """, "valor_compras_dia")
    devol = _sql_agregado_diario(extractor.engine, """
        SELECT df.fecha_completa AS ds, SUM(fd.total_linea_devolucion) AS valor_devoluciones_dia
        FROM edw.fact_devoluciones fd
        JOIN edw.dim_fecha df ON fd.fecha_sk = df.fecha_sk
        GROUP BY df.fecha_completa ORDER BY df.fecha_completa;
    """, "valor_devoluciones_dia")
    return pd.concat([compras, devol], axis=1)


def z_robusto_trailing(y: pd.Series, ventana: int) -> pd.Series:
    """z-score robusto de cada dia contra la mediana/MAD de los `ventana` dias ANTERIORES
    (shift 1: la historia disponible al momento de predecir, sin mirar el propio dia)."""
    mediana = y.shift(1).rolling(ventana, min_periods=7).median()
    mad = (y.shift(1) - mediana).abs().rolling(ventana, min_periods=7).median()
    return (y - mediana) / (1.4826 * mad.replace(0, np.nan))


def preparar_datasets():
    extractor = SalesTimeSerieExtractor()
    df_raw = extractor.fetch_daily_sales()
    exog = fetch_exogenas_candidatas(extractor)

    pipeline = build_preprocessing_pipeline()
    df = pipeline.fit_transform(df_raw)

    # Exogenas candidatas: alinear al indice de dias con venta y rezagar 1 dia (contemporaneas
    # del mismo dia del target no estarian disponibles al predecir -- mismo criterio que
    # COLUMNAS_EXOGENAS_CONTEMPORANEAS en build_features.py).
    for col in ("valor_compras_dia", "valor_devoluciones_dia"):
        serie = exog[col].reindex(df.index).fillna(0.0)
        df[f"{col.replace('_dia', '')}_prev"] = serie.shift(1).fillna(0.0)

    # Flags de pico atipico (solo con historia, shift 1)
    z = z_robusto_trailing(df["y_sales_net"], VENTANA_Z)
    es_pico = (z > Z_ROBUSTO_UMBRAL).astype(int)
    df["pico_prev"] = es_pico.shift(1).fillna(0).astype(int)
    df["n_picos_7d"] = es_pico.shift(1).rolling(7, min_periods=1).sum().fillna(0)
    df["_es_pico_hoy"] = es_pico  # columna auxiliar SOLO para la estrategia D (no es feature)

    fecha_corte = df.index.max() - pd.DateOffset(years=VENTANA_ANIOS)
    df = df.loc[df.index >= fecha_corte]
    train_size = int(len(df) * 0.8)
    return df.iloc[:train_size], df.iloc[train_size:]


def evaluar(nombre, X_train, y_train, X_test, y_test):
    resultados = []
    for seed in SEEDS:
        model = TransformedTargetRegressor(
            regressor=RandomForestRegressor(n_estimators=200, random_state=seed, n_jobs=-1),
            func=np.log1p, inverse_func=np.expm1,
        )
        model.fit(X_train, y_train)
        resultados.append(evaluate_reg(y_test, model.predict(X_test)))
    r2 = [r["R2"] for r in resultados]
    mae = [r["MAE"] for r in resultados]
    rmse = [r["RMSE"] for r in resultados]
    print(f"{nombre:32s} R2={np.mean(r2):+.4f}±{np.std(r2):.4f}  "
          f"MAE={np.mean(mae):8.2f}±{np.std(mae):6.2f}  RMSE={np.mean(rmse):8.2f}±{np.std(rmse):6.2f}  "
          f"({X_train.shape[1]} feats, {len(X_train)} filas train)")
    return {"config": nombre, "r2": np.mean(r2), "r2_std": np.std(r2),
            "mae": np.mean(mae), "rmse": np.mean(rmse)}


def main():
    df_train, df_test = preparar_datasets()
    X_train_full, y_train = select_features_and_target(df_train, "y_sales_net")
    X_test_full, y_test = select_features_and_target(df_test, "y_sales_net")

    cols_baseline = [c for c in X_train_full.columns if c not in (
        "valor_compras_prev", "valor_devoluciones_prev", "pico_prev", "n_picos_7d", "_es_pico_hoy")]
    cols_depurado = [c for c in cols_baseline if c not in FEATURES_A_REMOVER_DEPURADO]

    print(f"Train {len(X_train_full)} filas ({df_train.index.min().date()} -> {df_train.index.max().date()}) | "
          f"Test {len(X_test_full)} filas ({df_test.index.min().date()} -> {df_test.index.max().date()})")
    print(f"Protocolo: RF(n_estimators=200) x {len(SEEDS)} semillas {SEEDS}, TTR log1p, holdout completo\n")

    filas = []
    filas.append(evaluar("A. baseline (26 feats)", X_train_full[cols_baseline], y_train, X_test_full[cols_baseline], y_test))
    filas.append(evaluar("B. depurado (-8 feats)", X_train_full[cols_depurado], y_train, X_test_full[cols_depurado], y_test))
    filas.append(evaluar("C. baseline + flags de pico", X_train_full[cols_baseline + ["pico_prev", "n_picos_7d"]], y_train,
                         X_test_full[cols_baseline + ["pico_prev", "n_picos_7d"]], y_test))

    # D: excluir del TRAIN los dias atipicos (z robusto > umbral); holdout intacto.
    mask_no_pico = df_train["_es_pico_hoy"] == 0
    n_exc = int((~mask_no_pico).sum())
    filas.append(evaluar(f"D. train sin {n_exc} dias pico", X_train_full.loc[mask_no_pico, cols_baseline],
                         y_train.loc[mask_no_pico], X_test_full[cols_baseline], y_test))

    filas.append(evaluar("E. baseline + compras_prev", X_train_full[cols_baseline + ["valor_compras_prev"]], y_train,
                         X_test_full[cols_baseline + ["valor_compras_prev"]], y_test))
    filas.append(evaluar("F. baseline + devoluciones_prev", X_train_full[cols_baseline + ["valor_devoluciones_prev"]], y_train,
                         X_test_full[cols_baseline + ["valor_devoluciones_prev"]], y_test))

    out = Path(__file__).resolve().parent / "output_22"
    out.mkdir(exist_ok=True)
    pd.DataFrame(filas).to_csv(out / "exp_features_fase1.csv", index=False)


if __name__ == "__main__":
    main()
