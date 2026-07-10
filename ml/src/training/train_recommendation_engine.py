# ml/src/training/train_recommendation_engine.py
import logging

import pandas as pd

from src.utils.model_export import library_versions, save_artifact

logger = logging.getLogger("ML.Recommendation")


def train_association_rules(df_invoices: pd.DataFrame, min_support=0.01):
    """Reglas de asociación DIRECCIONALES (A->B y B->A) con support/confidence/lift sobre
    canastas de productos comprados juntos, usando la llave de negocio del producto
    (`product_code` = `codart`), no el nombre.

    H-10 (docs/auditoria/11_auditoria_tecnica_modelos_ml.md): el motor legacy generaba
    solo pares simétricos ordenados alfabéticamente con soporte (sin confidence ni lift);
    el backend filtraba solo por `item_A`, perdiendo ~50% de las recomendaciones donde el
    ítem comprado quedaba como `item_B`. Aquí se emite una fila por dirección, así el
    serving puede filtrar por cualquiera de las dos columnas sin perder cobertura.
    """
    logger.info("Construyendo reglas de asociación direccionales (Market Basket)...")

    if df_invoices.empty or 'transaction_id' not in df_invoices.columns or 'product_code' not in df_invoices.columns:
        logger.error("Dataframe inválido para Análisis Market-Basket (se esperan transaction_id, product_code).")
        return None

    basket = df_invoices.groupby('transaction_id')['product_code'].apply(lambda s: sorted(set(s))).reset_index()
    basket = basket[basket['product_code'].map(len) > 1]
    total_invoices = len(basket)
    if total_invoices == 0:
        logger.error("No hay canastas con 2+ productos distintos.")
        return None

    item_counts: dict[str, int] = {}
    cooccurrence: dict[tuple[str, str], int] = {}
    for items in basket['product_code']:
        for item in items:
            item_counts[item] = item_counts.get(item, 0) + 1
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                pair = (items[i], items[j])  # ya vienen ordenados (sorted(set(...)))
                cooccurrence[pair] = cooccurrence.get(pair, 0) + 1

    rules = []
    for (item_a, item_b), count in cooccurrence.items():
        support = count / total_invoices
        if support < min_support:
            continue
        support_a = item_counts[item_a] / total_invoices
        support_b = item_counts[item_b] / total_invoices
        lift = support / (support_a * support_b)
        rules.append({'item_A': item_a, 'item_B': item_b, 'support': support,
                       'confidence': count / item_counts[item_a], 'lift': lift})
        rules.append({'item_A': item_b, 'item_B': item_a, 'support': support,
                       'confidence': count / item_counts[item_b], 'lift': lift})

    df_rules = pd.DataFrame(rules)
    if not df_rules.empty:
        df_rules = df_rules.sort_values(by=['item_A', 'lift'], ascending=[True, False]).reset_index(drop=True)

    logger.info(f"Generadas {len(df_rules)} reglas direccionales de asociación cruzada (Cross-Selling).")
    return df_rules


def save_recommendation_rules(rules_df: pd.DataFrame, filepath=None, n_transactions=None):
    save_artifact(
        rules_df, "recommendation.pkl", filepath=filepath,
        algorithm="co-ocurrencia direccional (support/confidence/lift)",
        features=["item_A", "item_B", "support", "confidence", "lift"],
        metrics={"n_reglas": len(rules_df)} if rules_df is not None else {},
        contract_name="recommendation",
        contract_version="0.1.0",
        library_versions_used=library_versions("pandas"),
        data_range={"n_transacciones_entrenamiento": n_transactions} if n_transactions else {},
        extra={"problema": "reglas_asociacion_market_basket", "clave_producto": "codart"},
    )
    logger.info(f"Reglas de Agrupación guardadas ({len(rules_df)} filas, clave=codart).")
