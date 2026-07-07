# ml/src/training/train_recommendation_engine.py
import logging
import os
import joblib
import pandas as pd
# Dado que scikit-learn no incluye Apriori de forma nativa, se programa 
# una heurística por Fuerza Bruta (Nativos de Pandas) para cálculo de Matriz de Co-Ocurrencias
# lo cual es suficiente y performante para el framework de Market-Basket hasta adquirir `mlxtend`

logger = logging.getLogger("ML.Recommendation")

def train_association_rules(df_invoices: pd.DataFrame, min_support=0.01):
    """
    Simulación o construcción de un motor de recomendación de items comprados juntos
    usando Matrices Suaves de Co-ocurrencia sobre facturas.
    df_invoices espera [numfac, codart, nombre_articulo]
    """
    logger.info("Construyendo matriz de reglas de asociación - Productos Comprados Juntos (Market Basket)...")
    
    if df_invoices.empty or 'transaction_id' not in df_invoices.columns or 'product_name' not in df_invoices.columns:
        logger.error("Dataframe inválido para Análisis Market-Basket.")
        return None
        
    # Paso 1: Obtener una lista de productos cruzados per factura. 
    # Solo las facturas con 2+ atributos
    try:
        basket = df_invoices.groupby('transaction_id')['product_name'].apply(list).reset_index()
        basket = basket[basket['product_name'].map(len) > 1]
    except Exception as e:
        logger.error(f"Fallo agrupar matriz: {e}")
        return None

    # Implementación manual básica de co-ocurrencia (similar a FP-Growth)
    # Por rapidez y carencia de dependencias nativas complejas
    cooccurrence = {}
    for items in basket['product_name']:
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                item_a, item_b = sorted([items[i], items[j]])
                pair = (item_a, item_b)
                cooccurrence[pair] = cooccurrence.get(pair, 0) + 1

    # Filtrar por un min_support heuristico
    total_invoices = len(basket)
    rules = []
    
    for (item_a, item_b), count in cooccurrence.items():
        support = count / total_invoices
        if support >= min_support:
            rules.append({
                'item_A': item_a,
                'item_B': item_b,
                'co_occurrences': count,
                'support': support
            })
            
    df_rules = pd.DataFrame(rules)
    if not df_rules.empty:
        df_rules = df_rules.sort_values(by='co_occurrences', ascending=False)
        
    logger.info(f"Generadas {len(df_rules)} reglas de asociación cruzada (Cross-Selling).")
    return df_rules

def save_recommendation_rules(rules_df: pd.DataFrame, filepath=None):
    if filepath is None:
        filepath = os.path.join(os.getenv("ML_MODELS_DIR", "./models"), "association_rules.pkl")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    joblib.dump(rules_df, filepath)
    logger.info(f"Reglas de Agrupación guardadas en: {filepath}")
