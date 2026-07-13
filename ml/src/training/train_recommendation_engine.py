# ml/src/training/train_recommendation_engine.py
"""Motor de venta cruzada: candidatos competidores del re-análisis de Fase 3
(docs/features/plan_modulo_cross_selling.md §2.3.c) y el guardado del ganador.

Todas las estrategias exponen su salida en el mismo esquema unificado (contrato
`recommendation` v0.2.0, ml/contracts/models/recommendation.json):
`item_A` (contexto), `item_B` (recomendado), `score` (mayor=mejor, comparable entre
estrategias solo de forma ordinal -- NO es la misma escala matemática entre fuentes),
`fuente` (origen, para el texto de "motivo" en el backend), `support`/`confidence`
(NULL cuando no aplica, p.ej. item-item o popularidad).

Esto permite que `recomendar_desde_reglas` (y el ensamblador híbrido) traten cualquier
candidato de forma genérica, y que el backtest (`backtest_recommendation.py`) compita
todas las estrategias con la misma función de evaluación.
"""
import logging

import numpy as np
import pandas as pd

from src.utils.model_export import library_versions, save_artifact

logger = logging.getLogger("ML.Recommendation")

COLUMNAS_UNIFICADAS = ["item_A", "item_B", "score", "fuente", "support", "confidence"]


# ---------------------------------------------------------------------------
# Candidato 1: co-ocurrencia direccional (manual, línea base v0.1.0 re-tuneada)
# ---------------------------------------------------------------------------
def construir_reglas_coocurrencia(
    df_invoices: pd.DataFrame,
    min_support: float = 0.005,
    min_lift: float | None = None,
    min_confidence: float | None = None,
) -> pd.DataFrame | None:
    """Reglas de asociación DIRECCIONALES (A->B y B->A) con support/confidence/lift sobre
    canastas de productos comprados juntos, usando la llave de negocio del producto
    (`product_code` = `codart`), no el nombre.

    H-10 (docs/auditoria/11_auditoria_tecnica_modelos_ml.md): el motor legacy generaba
    solo pares simétricos ordenados alfabéticamente con soporte (sin confidence ni lift);
    el backend filtraba solo por `item_A`, perdiendo ~50% de las recomendaciones donde el
    ítem comprado quedaba como `item_B`. Aquí se emite una fila por dirección, así el
    serving puede filtrar por cualquiera de las dos columnas sin perder cobertura.

    Fase 3 (re-análisis, plan cross-selling): se agregan umbrales opcionales de
    `min_lift`/`min_confidence` -- v0.1.0 no filtraba por ninguno de los dos, solo por
    `min_support`, lo que dejaba pasar reglas de alto soporte pero afinidad débil
    (lift cercano a 1, casi pura popularidad).
    """
    logger.info(
        f"Construyendo reglas de co-ocurrencia (min_support={min_support}, "
        f"min_lift={min_lift}, min_confidence={min_confidence})..."
    )

    if df_invoices.empty or "transaction_id" not in df_invoices.columns or "product_code" not in df_invoices.columns:
        logger.error("Dataframe inválido para Análisis Market-Basket (se esperan transaction_id, product_code).")
        return None

    basket = df_invoices.groupby("transaction_id")["product_code"].apply(lambda s: sorted(set(s))).reset_index()
    basket = basket[basket["product_code"].map(len) > 1]
    total_invoices = len(basket)
    if total_invoices == 0:
        logger.error("No hay canastas con 2+ productos distintos.")
        return None

    item_counts: dict[str, int] = {}
    cooccurrence: dict[tuple[str, str], int] = {}
    for items in basket["product_code"]:
        for item in items:
            item_counts[item] = item_counts.get(item, 0) + 1
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                pair = (items[i], items[j])  # ya vienen ordenados (sorted(set(...)))
                cooccurrence[pair] = cooccurrence.get(pair, 0) + 1

    rows = []
    for (item_a, item_b), count in cooccurrence.items():
        support = count / total_invoices
        if support < min_support:
            continue
        support_a = item_counts[item_a] / total_invoices
        support_b = item_counts[item_b] / total_invoices
        lift = support / (support_a * support_b)
        conf_ab = count / item_counts[item_a]
        conf_ba = count / item_counts[item_b]
        if min_lift is not None and lift < min_lift:
            continue
        # El umbral de confidence se evalúa POR DIRECCIÓN (cada fila es una regla A->B
        # independiente); una dirección puede pasar el umbral aunque la opuesta no.
        if min_confidence is None or conf_ab >= min_confidence:
            rows.append({"item_A": item_a, "item_B": item_b, "score": lift, "fuente": "coocurrencia",
                         "support": support, "confidence": conf_ab})
        if min_confidence is None or conf_ba >= min_confidence:
            rows.append({"item_A": item_b, "item_B": item_a, "score": lift, "fuente": "coocurrencia",
                         "support": support, "confidence": conf_ba})

    df_rules = pd.DataFrame(rows, columns=COLUMNAS_UNIFICADAS)
    if not df_rules.empty:
        df_rules = df_rules.sort_values(by=["item_A", "score"], ascending=[True, False]).reset_index(drop=True)

    logger.info(f"Generadas {len(df_rules)} reglas direccionales de co-ocurrencia.")
    return df_rules


# Alias retrocompatible: firma y comportamiento idénticos a la versión pre-Fase 3
# (mismo algoritmo, sin umbrales de lift/confidence) para no romper llamadas existentes.
def train_association_rules(df_invoices: pd.DataFrame, min_support: float = 0.01) -> pd.DataFrame | None:
    df = construir_reglas_coocurrencia(df_invoices, min_support=min_support)
    if df is None or df.empty:
        return df
    # Formato legacy v0.1.0 (item_A, item_B, support, confidence, lift) para compatibilidad
    # con el serving actual (Fase 4 del plan actualiza esto a leer `score`/`fuente`).
    return df.rename(columns={"score": "lift"})[["item_A", "item_B", "support", "confidence", "lift"]]


# ---------------------------------------------------------------------------
# Candidato 2: Apriori/FP-Growth (mlxtend) -- itemsets de tamaño 2 (pares), misma
# métrica que la co-ocurrencia manual, para comparar la implementación de librería
# contra la manual con el MISMO umbral (el plan la exige como candidato explícito
# aunque el resultado matemático de pares sea equivalente -- ver notas del reporte).
# ---------------------------------------------------------------------------
def construir_reglas_apriori(
    df_invoices: pd.DataFrame,
    min_support: float = 0.005,
    min_lift: float | None = None,
    min_confidence: float | None = None,
) -> pd.DataFrame | None:
    from mlxtend.frequent_patterns import fpgrowth
    from mlxtend.preprocessing import TransactionEncoder

    if df_invoices.empty:
        return None
    basket = df_invoices.groupby("transaction_id")["product_code"].apply(lambda s: sorted(set(s)))
    basket = basket[basket.map(len) > 1]
    if basket.empty:
        logger.error("No hay canastas con 2+ productos distintos para Apriori/FP-Growth.")
        return None

    te = TransactionEncoder()
    te_array = te.fit(basket).transform(basket, sparse=True)
    onehot = pd.DataFrame.sparse.from_spmatrix(te_array, columns=te.columns_)

    itemsets = fpgrowth(onehot, min_support=min_support, use_colnames=True, max_len=2)
    if itemsets.empty:
        logger.error("FP-Growth no encontró itemsets frecuentes con ese min_support.")
        return None

    support_1 = {}
    for _, row in itemsets[itemsets["itemsets"].map(len) == 1].iterrows():
        (item,) = tuple(row["itemsets"])
        support_1[item] = row["support"]

    rows = []
    for _, row in itemsets[itemsets["itemsets"].map(len) == 2].iterrows():
        item_a, item_b = tuple(row["itemsets"])
        support_ab = row["support"]
        support_a = support_1.get(item_a)
        support_b = support_1.get(item_b)
        if not support_a or not support_b:
            continue
        lift = support_ab / (support_a * support_b)
        conf_ab = support_ab / support_a
        conf_ba = support_ab / support_b
        if min_lift is not None and lift < min_lift:
            continue
        if min_confidence is None or conf_ab >= min_confidence:
            rows.append({"item_A": item_a, "item_B": item_b, "score": lift, "fuente": "apriori",
                         "support": support_ab, "confidence": conf_ab})
        if min_confidence is None or conf_ba >= min_confidence:
            rows.append({"item_A": item_b, "item_B": item_a, "score": lift, "fuente": "apriori",
                         "support": support_ab, "confidence": conf_ba})

    df_rules = pd.DataFrame(rows, columns=COLUMNAS_UNIFICADAS)
    if not df_rules.empty:
        df_rules = df_rules.sort_values(by=["item_A", "score"], ascending=[True, False]).reset_index(drop=True)
    logger.info(f"Generadas {len(df_rules)} reglas direccionales vía FP-Growth (mlxtend).")
    return df_rules


# ---------------------------------------------------------------------------
# Candidato 3: filtrado colaborativo item-item (similitud coseno, scikit-learn).
# Matriz cliente x producto (incidencia binaria, "el cliente compró este producto
# ALGUNA VEZ") -- a diferencia de la co-ocurrencia, esto captura afinidad de un mismo
# cliente en FACTURAS DISTINTAS, que las reglas de canasta no ven (H25-5, no usa
# `surprise`, descartado por auditoría 25).
# ---------------------------------------------------------------------------
def construir_item_item(df_lines: pd.DataFrame, top_k_vecinos: int = 20, min_clientes_por_producto: int = 5) -> pd.DataFrame | None:
    from scipy.sparse import csr_matrix
    from sklearn.metrics.pairwise import cosine_similarity

    if "cliente_sk" not in df_lines.columns:
        logger.error("fetch_market_basket debe incluir cliente_sk para el candidato item-item.")
        return None

    # Centinela de cliente desconocido (regla de negocio 12, CLAUDE.md): un cliente_sk=-1
    # agregaría un pseudo-usuario con TODAS las compras anónimas, distorsionando la
    # similitud (afinidad falsa entre productos que solo comparten el "cliente" -1).
    df_cf = df_lines.loc[df_lines["cliente_sk"] != -1, ["cliente_sk", "product_code"]].drop_duplicates()
    if df_cf.empty:
        logger.error("No hay líneas con cliente_sk válido para construir la matriz item-item.")
        return None

    productos_validos = df_cf["product_code"].value_counts()
    productos_validos = productos_validos[productos_validos >= min_clientes_por_producto].index
    df_cf = df_cf[df_cf["product_code"].isin(productos_validos)]
    if df_cf.empty:
        logger.error("Ningún producto alcanza min_clientes_por_producto para item-item.")
        return None

    clientes = df_cf["cliente_sk"].astype("category")
    productos = df_cf["product_code"].astype("category")
    mat = csr_matrix(
        (np.ones(len(df_cf), dtype=np.float32), (productos.cat.codes, clientes.cat.codes)),
        shape=(len(productos.cat.categories), len(clientes.cat.categories)),
    )
    sim = cosine_similarity(mat, dense_output=False).tocsr()
    codigos = productos.cat.categories.to_numpy()

    rows = []
    for idx in range(sim.shape[0]):
        fila = sim.getrow(idx).toarray().ravel()
        fila[idx] = -1.0  # excluir auto-similitud
        vecinos_idx = np.argsort(fila)[::-1][:top_k_vecinos]
        for v in vecinos_idx:
            score = fila[v]
            if score <= 0:
                continue
            rows.append({"item_A": codigos[idx], "item_B": codigos[v], "score": float(score),
                         "fuente": "item_item", "support": None, "confidence": None})

    df_rules = pd.DataFrame(rows, columns=COLUMNAS_UNIFICADAS)
    logger.info(f"Generadas {len(df_rules)} relaciones item-item (top-{top_k_vecinos} vecinos por producto, similitud coseno).")
    return df_rules


# ---------------------------------------------------------------------------
# Fallback: popularidad por categoría (usado como última red del híbrido cuando ni
# reglas ni item-item cubren el contexto).
# ---------------------------------------------------------------------------
def construir_popularidad_categoria(df_lines: pd.DataFrame, catalogo: pd.DataFrame) -> pd.DataFrame:
    conteo = df_lines["product_code"].value_counts().rename("frecuencia").reset_index()
    conteo.columns = ["product_code", "frecuencia"]
    conteo = conteo.merge(catalogo[["product_code", "categoria"]], on="product_code", how="left")
    conteo["score"] = conteo.groupby("categoria")["frecuencia"].transform(lambda s: s / s.max())
    return conteo[["product_code", "categoria", "score"]].sort_values(["categoria", "score"], ascending=[True, False])


# ---------------------------------------------------------------------------
# Recomendadores genéricos (usados por el backtest y, potencialmente, por el serving)
# ---------------------------------------------------------------------------
def recomendar_desde_reglas(rules_df: pd.DataFrame, contexto: list[str], top_n: int) -> list[str]:
    if rules_df is None or rules_df.empty:
        return []
    candidatas = rules_df[rules_df["item_A"].isin(contexto) & ~rules_df["item_B"].isin(contexto)]
    if candidatas.empty:
        return []
    agregadas = candidatas.groupby("item_B")["score"].max().sort_values(ascending=False)
    return agregadas.index.tolist()[:top_n]


def recomendar_popularidad(popularidad_df: pd.DataFrame, contexto: list[str], top_n: int, categorias_contexto: set[str] | None = None) -> list[str]:
    if popularidad_df is None or popularidad_df.empty:
        return []
    pool = popularidad_df[~popularidad_df["product_code"].isin(contexto)]
    if categorias_contexto:
        en_categoria = pool[pool["categoria"].isin(categorias_contexto)]
        if not en_categoria.empty:
            pool = en_categoria
    return pool.sort_values("score", ascending=False)["product_code"].head(top_n).tolist()


def recomendar_hibrido(
    reglas_df: pd.DataFrame,
    item_item_df: pd.DataFrame,
    popularidad_df: pd.DataFrame,
    contexto: list[str],
    top_n: int,
    codart_a_categoria: dict[str, str] | None = None,
) -> list[str]:
    """Reglas de canasta (fuente primaria) -> item-item (segunda fuente) -> popularidad
    por categoría (fallback final), sin duplicados, respetando el orden de prioridad."""
    sugerencias: list[str] = []

    def _agregar(nuevas: list[str]):
        for cod in nuevas:
            if cod not in sugerencias and cod not in contexto:
                sugerencias.append(cod)
            if len(sugerencias) >= top_n:
                break

    _agregar(recomendar_desde_reglas(reglas_df, contexto, top_n))
    if len(sugerencias) < top_n:
        _agregar(recomendar_desde_reglas(item_item_df, contexto, top_n - len(sugerencias)))
    if len(sugerencias) < top_n and codart_a_categoria:
        categorias_contexto = {codart_a_categoria[c] for c in contexto if c in codart_a_categoria}
        _agregar(recomendar_popularidad(popularidad_df, contexto + sugerencias, top_n - len(sugerencias), categorias_contexto))
    return sugerencias[:top_n]


# ---------------------------------------------------------------------------
# Guardado del artefacto ganador (contrato v0.2.0, esquema unificado)
# ---------------------------------------------------------------------------
def save_recommendation_rules(
    rules_df: pd.DataFrame,
    filepath: str | None = None,
    n_transactions: int | None = None,
    algorithm: str = "co-ocurrencia direccional (support/confidence/lift)",
    contract_version: str = "0.2.0",
    metrics: dict | None = None,
    data_range: dict | None = None,
    extra: dict | None = None,
) -> None:
    save_artifact(
        rules_df,
        "recommendation.pkl",
        filepath=filepath,
        algorithm=algorithm,
        features=COLUMNAS_UNIFICADAS,
        metrics=metrics or {"n_reglas": len(rules_df)},
        contract_name="recommendation",
        contract_version=contract_version,
        library_versions_used=library_versions("pandas", "scikit-learn", "mlxtend"),
        data_range=data_range or ({"n_transacciones_entrenamiento": n_transactions} if n_transactions else {}),
        extra=extra or {"problema": "venta_cruzada_top_n", "clave_producto": "codart"},
    )
    logger.info(f"Reglas de recomendación guardadas ({len(rules_df)} filas, clave=codart).")
