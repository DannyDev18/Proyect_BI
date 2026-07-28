# ml/src/utils/stats_baseline.py
"""Baseline estadístico OLS de referencia (Fase 4, docs/features/plan_mejora_pipeline_ml.md
§6): un modelo ML que no supere claramente un OLS simple sobre las mismas variables es una
señal de alerta, y el `summary()` de `statsmodels` da diagnósticos (p-values, R² ajustado,
F-test, VIF) que un RandomForest/CatBoost no expone. Dependencia SOLO de entrenamiento
(`ml/requirements.txt`) -- nunca se sirve desde el backend ni se serializa en los .pkl.

No reemplaza al modelo ML ganador: es un diagnóstico que se guarda junto al artefacto
(sidecar de texto + resumen numérico en el `.meta.json`) para la model card (Fase 5).
"""
import logging
import os
import re

import pandas as pd
import statsmodels.formula.api as smf
from statsmodels.stats.outliers_influence import variance_inflation_factor

logger = logging.getLogger("ML.StatsBaseline")


def _nombre_columna_segura(col: str) -> str:
    """`smf.ols` usa Patsy para parsear la fórmula: nombres de columna con espacios,
    guiones o que empiezan con dígito rompen el parser. Se sanea a un identificador
    válido de Python solo para la fórmula; el DataFrame se renombra de forma temporal."""
    seguro = re.sub(r"\W", "_", col)
    if seguro[0].isdigit():
        seguro = f"c_{seguro}"
    return seguro


def fit_ols_baseline(
    df_train: pd.DataFrame,
    feature_cols: list[str],
    target_col: str,
    *,
    max_features_vif: int = 20,
) -> dict:
    """Ajusta `target_col ~ feature_cols` con `smf.ols(...).fit()` sobre el split de
    entrenamiento (mismo split cronológico 80/20 que el modelo ML, nunca sobre el
    holdout). Devuelve un dict con el `summary()` como texto, R² ajustado, F-test y VIF
    (solo columnas numéricas; hasta `max_features_vif` para no disparar el costo O(n²)
    de VIF en datasets con muchas features).

    Solo usa columnas numéricas de `feature_cols` (dtype float/int) -- las categóricas
    ya vienen one-hot/encoded en `df_train` por el pipeline de features, así que no se
    necesita `C(...)` de Patsy aquí.
    """
    columnas_numericas = [
        c for c in feature_cols
        if c in df_train.columns and pd.api.types.is_numeric_dtype(df_train[c])
    ]
    if not columnas_numericas:
        return {"error": "sin columnas numéricas para el baseline OLS"}

    data = df_train[columnas_numericas + [target_col]].dropna().copy()
    if len(data) < len(columnas_numericas) + 2:
        return {"error": "filas insuficientes tras dropna para ajustar OLS"}

    mapa_seguro = {c: _nombre_columna_segura(c) for c in columnas_numericas}
    mapa_seguro[target_col] = _nombre_columna_segura(target_col)
    data = data.rename(columns=mapa_seguro)
    target_seguro = mapa_seguro[target_col]
    features_seguras = [mapa_seguro[c] for c in columnas_numericas]

    formula = f"{target_seguro} ~ {' + '.join(features_seguras)}"
    try:
        resultado = smf.ols(formula=formula, data=data).fit()
    except Exception as exc:
        logger.warning(f"No se pudo ajustar el baseline OLS: {exc}")
        return {"error": str(exc)}

    vif = {}
    columnas_vif = features_seguras[:max_features_vif]
    if len(columnas_vif) >= 2:
        X_vif = data[columnas_vif].assign(_const=1.0)
        for i, col in enumerate(columnas_vif):
            try:
                vif[col] = float(variance_inflation_factor(X_vif.values, i))
            except Exception:
                vif[col] = None

    return {
        "formula": formula,
        "summary_text": resultado.summary().as_text(),
        "r2": float(resultado.rsquared),
        "r2_ajustado": float(resultado.rsquared_adj),
        "f_statistic": float(resultado.fvalue) if resultado.fvalue is not None else None,
        "f_pvalue": float(resultado.f_pvalue) if resultado.f_pvalue is not None else None,
        "n_observaciones": int(resultado.nobs),
        "vif": vif,
        "p_values_significativas": {
            col: float(p) for col, p in resultado.pvalues.items() if p < 0.05
        },
    }


def guardar_diagnostico_ols(clave: str, resultado: dict, models_dir: str) -> str | None:
    """Escribe el `summary()` completo a un .txt junto a los artefactos (para la model
    card, Fase 5) y devuelve la ruta relativa a incluir en el sidecar `.meta.json`."""
    if "summary_text" not in resultado:
        return None
    diagnostics_dir = os.path.join(models_dir, "diagnostics")
    os.makedirs(diagnostics_dir, exist_ok=True)
    ruta = os.path.join(diagnostics_dir, f"{clave}_ols_baseline.txt")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(resultado["summary_text"])
    return ruta
