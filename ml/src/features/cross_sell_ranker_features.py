# ml/src/features/cross_sell_ranker_features.py
"""Construcción de features y dataset de entrenamiento para `cross_sell_ranker` (Fase 2,
docs/features/plan_refactor_venta_cruzada_ia.md). Reutiliza el patrón de cortes
temporales de `fetch_churn_data` (H-05: features con datos <= T, etiqueta en (T, T+h])
y el generador de candidatos `recomendar_desde_reglas` ya entrenado (`recommendation.pkl`)
para que los negativos sean "lo que el item-item habría propuesto en T", no productos
aleatorios de todo el catálogo (eso solo enseñaría a distinguir "plausible" de
"irrelevante", que el item-item ya hace).

`construir_features_candidatos` es la pieza compartida entre la construcción del
dataset de entrenamiento y el re-ranking del backtest (§2.4 del plan): ambos deben
calcular las features EXACTAMENTE igual para que el backtest mida lo que el modelo
realmente aprendió.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from src.training.train_recommendation_engine import recomendar_desde_reglas

logger = logging.getLogger("ML.CrossSellRankerFeatures")

FEATURE_COLUMNS = [
    "score_item_item", "misma_categoria_que_canasta", "recency", "frequency",
    "monetary_value", "average_ticket", "margen_relativo", "precio_relativo_categoria",
    "ventas_7d_norm", "ventas_30d_norm", "ventas_90d_norm", "mes", "semana_anio",
    "ya_compro_categoria", "dias_desde_ultima_compra_categoria", "sucursal",
]

SENTINELA_SIN_COMPRA_CATEGORIA = 9999.0


def calcular_rfm_a_corte(hist: pd.DataFrame, corte: pd.Timestamp) -> pd.DataFrame:
    """RFM por cliente con datos <= corte (misma semántica que `fetch_churn_data`)."""
    rfm = hist.groupby("cliente_sk").agg(
        ultima_compra=("fecha", "max"),
        frequency=("fecha", "nunique"),
        monetary_value=("subtotal_neto", "sum"),
    )
    rfm["recency"] = (corte - rfm["ultima_compra"]).dt.days.astype(float)
    rfm["average_ticket"] = rfm["monetary_value"] / rfm["frequency"]
    return rfm


def calcular_ventas_por_producto_ventanas(hist: pd.DataFrame, corte: pd.Timestamp) -> pd.DataFrame:
    """Líneas del producto en (corte-7d,corte]/(corte-30d,corte]/(corte-90d,corte],
    normalizadas por su promedio histórico mensual de líneas hasta el corte (mínimo 1
    para no dividir por cero) -- señal de estacionalidad de corto plazo (§2.3 del plan:
    el modelo aprende el peso, no hay artefacto por ventana)."""
    total_dias = max((hist["fecha"].max() - hist["fecha"].min()).days, 1)
    meses_historia = max(total_dias / 30.0, 1.0)
    prom_mensual = (hist.groupby("codart").size() / meses_historia).rename("prom_mensual").clip(lower=1e-6)

    resultado = prom_mensual.to_frame()
    for ventana, col in ((7, "ventas_7d_norm"), (30, "ventas_30d_norm"), (90, "ventas_90d_norm")):
        ventana_df = hist.loc[hist["fecha"] > corte - pd.Timedelta(days=ventana)]
        conteo = ventana_df.groupby("codart").size()
        resultado[col] = (conteo / resultado["prom_mensual"]).fillna(0.0)
    return resultado[["ventas_7d_norm", "ventas_30d_norm", "ventas_90d_norm"]]


def calcular_economia_catalogo(catalogo: pd.DataFrame) -> pd.DataFrame:
    """margen_relativo/precio_relativo_categoria por `product_code` (catálogo vigente,
    ver `known_serving_mismatch` del contrato -- no se reconstruye el precio histórico)."""
    cat = catalogo.set_index("product_code").copy()
    cat["margen_relativo"] = np.where(
        (cat["costo_promedio"].notna()) & (cat["costo_promedio"] > 0) & (cat["precio_oficial"] > 0),
        (cat["precio_oficial"] - cat["costo_promedio"]) / cat["precio_oficial"],
        0.0,
    )
    precio_medio_categoria = cat.groupby("categoria")["precio_oficial"].transform("mean").replace(0, np.nan)
    cat["precio_relativo_categoria"] = (cat["precio_oficial"] / precio_medio_categoria).fillna(1.0)
    return cat[["categoria", "margen_relativo", "precio_relativo_categoria"]]


def construir_features_candidatos(
    hist_cliente: pd.DataFrame,
    hist_global: pd.DataFrame,
    candidatos: list[str],
    contexto: list[str],
    corte: pd.Timestamp,
    item_item_rules: pd.DataFrame,
    catalogo_economia: pd.DataFrame,
    ventas_ventanas: pd.DataFrame,
    rfm_cliente: pd.Series,
    sucursal_cliente,
) -> pd.DataFrame:
    """Features de un lote de candidatos para UN cliente en UN corte T. Compartida entre
    la construcción del dataset de entrenamiento y el re-ranking del backtest (§2.4)."""
    if not candidatos:
        return pd.DataFrame(columns=FEATURE_COLUMNS)

    categoria_contexto = None
    if contexto:
        cats_contexto = catalogo_economia.reindex(contexto)["categoria"].dropna()
        if not cats_contexto.empty:
            categoria_contexto = cats_contexto.mode().iat[0]

    scores_item_item: dict[str, float] = {}
    if contexto:
        reglas_contexto = item_item_rules[
            item_item_rules["item_A"].isin(contexto) & item_item_rules["item_B"].isin(candidatos)
        ]
        if not reglas_contexto.empty:
            scores_item_item = reglas_contexto.groupby("item_B")["score"].max().to_dict()

    categorias_compradas = set(hist_cliente["categoria"].dropna().unique()) if not hist_cliente.empty else set()
    ultima_compra_categoria = (
        hist_cliente.groupby("categoria")["fecha"].max() if not hist_cliente.empty else pd.Series(dtype="datetime64[ns]")
    )

    filas = []
    for codart in candidatos:
        econ = catalogo_economia.loc[codart] if codart in catalogo_economia.index else None
        categoria = econ["categoria"] if econ is not None else None
        ya_compro = categoria in categorias_compradas if categoria is not None else False
        if ya_compro:
            dias_desde = float((corte - ultima_compra_categoria[categoria]).days)
        else:
            dias_desde = SENTINELA_SIN_COMPRA_CATEGORIA

        ventanas = ventas_ventanas.loc[codart] if codart in ventas_ventanas.index else None

        filas.append({
            "codart": codart,
            "score_item_item": float(scores_item_item.get(codart, 0.0)),
            "misma_categoria_que_canasta": int(categoria is not None and categoria == categoria_contexto),
            "recency": float(rfm_cliente.get("recency", SENTINELA_SIN_COMPRA_CATEGORIA)),
            "frequency": float(rfm_cliente.get("frequency", 0.0)),
            "monetary_value": float(rfm_cliente.get("monetary_value", 0.0)),
            "average_ticket": float(rfm_cliente.get("average_ticket", 0.0)),
            "margen_relativo": float(econ["margen_relativo"]) if econ is not None else 0.0,
            "precio_relativo_categoria": float(econ["precio_relativo_categoria"]) if econ is not None else 1.0,
            "ventas_7d_norm": float(ventanas["ventas_7d_norm"]) if ventanas is not None else 0.0,
            "ventas_30d_norm": float(ventanas["ventas_30d_norm"]) if ventanas is not None else 0.0,
            "ventas_90d_norm": float(ventanas["ventas_90d_norm"]) if ventanas is not None else 0.0,
            "mes": int(corte.month),
            "semana_anio": int(corte.isocalendar().week),
            "ya_compro_categoria": int(ya_compro),
            "dias_desde_ultima_compra_categoria": dias_desde,
            "sucursal": str(sucursal_cliente),
        })
    return pd.DataFrame(filas).set_index("codart")


def construir_dataset_ranking(
    tx: pd.DataFrame,
    item_item_rules: pd.DataFrame,
    catalogo: pd.DataFrame,
    horizonte_dias: int,
    n_cortes: int,
    espaciado_dias: int,
    ratio_negativos: int,
    top_candidatos: int,
    seed: int = 42,
) -> pd.DataFrame:
    """Dataset (cliente, producto, corte) -> label, con las features de
    `FEATURE_COLUMNS` ya calculadas (excepto `p_abandono`/`segmento_rfm`, que se
    agregan en `ml/main.py` aplicando los modelos `churn_rf`/`segmentation` YA
    ENTRENADOS -- son features de entrada, no solo servicios aparte, decisión de
    arquitectura del plan §3).

    Positivos: producto comprado por PRIMERA VEZ por el cliente en (T, T+horizonte_dias].
    Negativos: candidatos que el item-item habría propuesto en T (a partir del contexto
    reciente del cliente) y que el cliente NO compró en esa ventana -- muestreados con
    `ratio_negativos` por positivo (nunca aleatorios de todo el catálogo, §2.2 del plan).
    Cortes ORDENADOS ascendente (para el split cronológico posterior en `ml/main.py`)."""
    rng = np.random.default_rng(seed)
    catalogo_economia = calcular_economia_catalogo(catalogo)
    productos_populares = tx["codart"].value_counts().index.tolist()

    max_date, min_date = tx["fecha"].max(), tx["fecha"].min()
    horizonte = pd.Timedelta(days=horizonte_dias)
    cortes = []
    corte = max_date - horizonte
    while corte - pd.Timedelta(days=espaciado_dias) >= min_date and len(cortes) < n_cortes:
        cortes.append(corte)
        corte = corte - pd.Timedelta(days=espaciado_dias)
    cortes = sorted(cortes)
    logger.info(f"Cortes de entrenamiento del ranker: {len(cortes)} ({cortes[0].date() if cortes else '-'}..{cortes[-1].date() if cortes else '-'})")

    frames = []
    for corte in cortes:
        hist = tx.loc[tx["fecha"] <= corte]
        futuro = tx.loc[(tx["fecha"] > corte) & (tx["fecha"] <= corte + horizonte)]
        if hist.empty or futuro.empty:
            continue

        rfm = calcular_rfm_a_corte(hist, corte)
        ventas_ventanas = calcular_ventas_por_producto_ventanas(hist, corte)
        ya_comprado = hist.groupby("cliente_sk")["codart"].apply(set)
        compras_futuras = futuro.groupby("cliente_sk")["codart"].apply(set)
        sucursal_habitual = hist.groupby("cliente_sk")["sucursal_sk"].agg(lambda s: s.mode().iat[0])
        contexto_reciente = (
            hist.sort_values("fecha").groupby("cliente_sk")["codart"].apply(lambda s: list(dict.fromkeys(s.tolist()[::-1]))[:5])
        )

        filas_corte = []
        for cliente_sk, productos_futuro in compras_futuras.items():
            ya = ya_comprado.get(cliente_sk, set())
            positivos = productos_futuro - ya
            if not positivos:
                continue

            contexto = contexto_reciente.get(cliente_sk, [])
            hist_cliente = hist.loc[hist["cliente_sk"] == cliente_sk]
            rfm_cliente = rfm.loc[cliente_sk] if cliente_sk in rfm.index else pd.Series(dtype=float)
            sucursal_cliente = sucursal_habitual.get(cliente_sk, -1)

            candidatos_item_item = recomendar_desde_reglas(item_item_rules, contexto, top_candidatos) if contexto else []
            pool_negativos = [
                c for c in candidatos_item_item
                if c not in ya and c not in positivos and c in catalogo_economia.index
            ]
            if len(pool_negativos) < ratio_negativos:
                # Respaldo por popularidad general (mismo criterio que el fallback de
                # producción, RN-CS1): asegura que siempre haya negativos "duros" aunque
                # el item-item no tenga candidatos para este contexto.
                respaldo = [
                    c for c in productos_populares
                    if c not in ya and c not in positivos and c not in pool_negativos and c in catalogo_economia.index
                ]
                pool_negativos.extend(respaldo[: max(0, ratio_negativos * 3 - len(pool_negativos))])

            n_negativos = min(len(pool_negativos), ratio_negativos * len(positivos))
            negativos = list(rng.choice(pool_negativos, size=n_negativos, replace=False)) if n_negativos > 0 else []

            candidatos_totales = list(positivos) + negativos
            candidatos_totales = [c for c in candidatos_totales if c in catalogo_economia.index]
            if not candidatos_totales:
                continue

            features = construir_features_candidatos(
                hist_cliente, hist, candidatos_totales, contexto, corte,
                item_item_rules, catalogo_economia, ventas_ventanas, rfm_cliente, sucursal_cliente,
            )
            features["cliente_sk"] = cliente_sk
            features["corte"] = corte
            features["label"] = [1 if c in positivos else 0 for c in features.index]
            filas_corte.append(features.reset_index())

        if filas_corte:
            frames.append(pd.concat(filas_corte, ignore_index=True))
        logger.info(f"  > Corte {corte.date()}: {sum(len(f) for f in filas_corte)} filas ({len(filas_corte)} clientes con positivo).")

    if not frames:
        return pd.DataFrame(columns=["cliente_sk", "codart", "corte", "label", *FEATURE_COLUMNS])
    return pd.concat(frames, ignore_index=True)


def preparar_matriz_features(df: pd.DataFrame, sucursal_valores: list[str]) -> pd.DataFrame:
    """Codifica `sucursal` (categórica) como one-hot contra un VOCABULARIO FIJO
    (aprendido una sola vez en el entrenamiento) -- las mismas columnas en
    entrenamiento y en el backtest/re-ranking, sin importar qué sucursales aparezcan
    en cada corte o canasta de test. `p_abandono`/`segmento_rfm` deben venir ya
    poblados en `df` (se calculan aplicando los modelos `churn_rf`/`segmentation` ya
    entrenados, fuera de este módulo -- ver `ml/main.py::train_cross_sell_ranker`)."""
    base_cols = [c for c in FEATURE_COLUMNS if c != "sucursal"] + ["p_abandono", "segmento_rfm"]
    resultado = df.reindex(columns=base_cols, fill_value=0.0).copy()
    sucursal_str = df["sucursal"].astype(str) if "sucursal" in df.columns else pd.Series("", index=df.index)
    for cod in sucursal_valores:
        resultado[f"sucursal_{cod}"] = (sucursal_str == str(cod)).astype(int)
    return resultado
