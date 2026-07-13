# ml/notebooks/experimentos_cross_selling.py
"""Fase 3 -- competencia de estrategias de venta cruzada con backtest temporal
(docs/features/plan_modulo_cross_selling.md §2.3.c/d).

Corre el grid experimental fijado en el EDA (ml/notebooks/eda_cross_selling.py, ver
notes de ml/contracts/models/recommendation.json v0.2.0) y compara TODOS los
candidatos con las mismas métricas: Precision@K/Recall@K (K=3,5), Hit-Rate@5,
cobertura e impacto en ticket. Imprime una tabla comparativa que se copia (ya
ejecutada) a ml/REPORTE_MEJORA_MODELOS.md -- este script es el experimento, no un
artefacto de producción.

Ejecutar dentro del contenedor `ml` (versiones pineadas, H-20):
    docker compose run --rm ml python notebooks/experimentos_cross_selling.py
"""
import logging
import sys

import pandas as pd

sys.path.insert(0, ".")
from src.data.make_dataset import SalesTimeSerieExtractor  # noqa: E402
from src.training.backtest_recommendation import (  # noqa: E402
    construir_canastas,
    evaluar_estrategia,
    split_temporal,
)
from src.training.train_recommendation_engine import (  # noqa: E402
    construir_item_item,
    construir_popularidad_categoria,
    construir_reglas_apriori,
    construir_reglas_coocurrencia,
    recomendar_desde_reglas,
    recomendar_hibrido,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ML.ExperimentosCrossSelling")

# Horizonte de test: último trimestre, igual definición que la línea base v0.1.0
# (auditoría 25 §1: "último trimestre" = >= 2026-04-13), para que la cobertura sea
# comparable directamente contra el 87.9% ya medido.
HORIZONTE_TEST_DIAS = 90


def main() -> None:
    ext = SalesTimeSerieExtractor()
    catalogo = ext.fetch_product_catalog()
    precios = dict(zip(catalogo["product_code"], catalogo["precio_oficial"].fillna(0.0)))
    codart_a_categoria = dict(zip(catalogo["product_code"], catalogo["categoria"]))

    resultados = []

    # El grid de ventana se evalúa cargando el dataset una vez por ventana (cada
    # ventana requiere una consulta distinta a fetch_market_basket). 8 años cubre
    # prácticamente todo el histórico (2018-01-02..2026-07-13, EDA §0) usando el MISMO
    # camino de código (filtro por fecha) que 2/3 años, en vez de un LIMIT-muestra aparte.
    for ventana_anios in (2, 3, 8):
        etiqueta_ventana = f"{ventana_anios}a"
        logger.info(f"=== Ventana temporal: {etiqueta_ventana} ===")
        df_basket = ext.fetch_market_basket(ventana_anios=ventana_anios)
        df_train, df_test = split_temporal(df_basket, horizonte_dias=HORIZONTE_TEST_DIAS)
        canastas_test = construir_canastas(df_test)
        if canastas_test.empty:
            logger.warning(f"Ventana {etiqueta_ventana}: sin canastas de test, se omite.")
            continue

        # --- Candidato 1: co-ocurrencia re-tuneada (grid de min_support x min_lift) ---
        for min_support in (0.001, 0.003, 0.005):
            for min_lift in (None, 1.5):
                reglas = construir_reglas_coocurrencia(df_train, min_support=min_support, min_lift=min_lift)
                if reglas is None or reglas.empty:
                    continue
                metricas = evaluar_estrategia(
                    lambda ctx, k, r=reglas: recomendar_desde_reglas(r, ctx, k),
                    canastas_test, precios=precios,
                )
                resultados.append({
                    "estrategia": "coocurrencia", "ventana": etiqueta_ventana,
                    "min_support": min_support, "min_lift": min_lift, "n_reglas": len(reglas),
                    **metricas.to_dict(),
                })

        # --- Candidato 2: Apriori/FP-Growth (mlxtend), mismo grid de min_support ---
        for min_support in (0.001, 0.003, 0.005):
            reglas_ap = construir_reglas_apriori(df_train, min_support=min_support)
            if reglas_ap is None or reglas_ap.empty:
                continue
            metricas = evaluar_estrategia(
                lambda ctx, k, r=reglas_ap: recomendar_desde_reglas(r, ctx, k),
                canastas_test, precios=precios,
            )
            resultados.append({
                "estrategia": "apriori_mlxtend", "ventana": etiqueta_ventana,
                "min_support": min_support, "min_lift": None, "n_reglas": len(reglas_ap),
                **metricas.to_dict(),
            })

        # --- Candidato 3: item-item (similitud coseno) ---
        item_item = construir_item_item(df_train, top_k_vecinos=20)
        if item_item is not None and not item_item.empty:
            metricas = evaluar_estrategia(
                lambda ctx, k, r=item_item: recomendar_desde_reglas(r, ctx, k),
                canastas_test, precios=precios,
            )
            resultados.append({
                "estrategia": "item_item", "ventana": etiqueta_ventana,
                "min_support": None, "min_lift": None, "n_reglas": len(item_item),
                **metricas.to_dict(),
            })

        # --- Candidato 4: híbrido (mejor co-ocurrencia de esta ventana + item-item + popularidad) ---
        mejor_reglas = construir_reglas_coocurrencia(df_train, min_support=0.001, min_lift=1.5)
        popularidad = construir_popularidad_categoria(df_train, catalogo)
        if mejor_reglas is not None and item_item is not None:
            metricas = evaluar_estrategia(
                lambda ctx, k: recomendar_hibrido(mejor_reglas, item_item, popularidad, ctx, k, codart_a_categoria),
                canastas_test, precios=precios,
            )
            resultados.append({
                "estrategia": "hibrido", "ventana": etiqueta_ventana,
                "min_support": 0.001, "min_lift": 1.5, "n_reglas": len(mejor_reglas) + len(item_item),
                **metricas.to_dict(),
            })

    df_resultados = pd.DataFrame(resultados)
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 20)
    print("\n" + "=" * 120)
    print("RESULTADOS DEL BACKTEST (línea base v0.1.0: cobertura=0.879, sin precision/recall medido)")
    print("=" * 120)
    cols = ["estrategia", "ventana", "min_support", "min_lift", "n_reglas", "n_canastas_test",
            "cobertura", "precision_at_3", "precision_at_5", "recall_at_3", "recall_at_5",
            "hit_rate_5", "impacto_ticket_medio"]
    print(df_resultados[cols].sort_values("precision_at_5", ascending=False).to_string(index=False))

    df_resultados.to_csv("/tmp/experimentos_cross_selling_resultados.csv", index=False)
    print("\nResultados también guardados en /tmp/experimentos_cross_selling_resultados.csv (dentro del contenedor)")


if __name__ == "__main__":
    main()
