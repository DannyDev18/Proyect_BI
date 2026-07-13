# ml/notebooks/publicar_ganador_cross_selling.py
"""Publica el artefacto ganador de la competencia de Fase 3 (venta cruzada) tras el
backtest en `experimentos_cross_selling.py`: filtrado colaborativo item-item
(similitud coseno, ventana de 2 años, top-20 vecinos) -- ganador por Precision@5 con
cobertura >= línea base (docs/features/plan_modulo_cross_selling.md §2.3.d).

A diferencia del backtest (que entrena solo hasta T para poder evaluar contra el
holdout), el artefacto de producción se entrena con TODA la ventana de 2 años
disponible (sin holdout) -- el backtest ya validó la estrategia, este paso solo
maximiza los datos usados para servir en producción.

Ejecutar dentro del contenedor `ml` (versiones pineadas, H-20):
    docker compose run --rm ml python notebooks/publicar_ganador_cross_selling.py
"""
import logging
import sys

sys.path.insert(0, ".")
from src.data.make_dataset import SalesTimeSerieExtractor  # noqa: E402
from src.training.train_recommendation_engine import construir_item_item, save_recommendation_rules  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ML.PublicarGanadorCrossSelling")

VENTANA_ANIOS_GANADORA = 2
TOP_K_VECINOS_GANADOR = 20

# Métricas reales del backtest temporal (experimentos_cross_selling.py, corte 2026-04-14,
# train=2024-07-13..2026-04-14, test=2026-04-14..2026-07-13, 4169 canastas de test):
METRICAS_BACKTEST_GANADOR = {
    "precision_at_3": 0.0975,
    "precision_at_5": 0.0769,
    "recall_at_3": 0.1999,
    "recall_at_5": 0.2624,
    "hit_rate_5": 0.3579,
    "cobertura": 0.9791,
    "impacto_ticket_medio": 23.65,
}


def main() -> None:
    ext = SalesTimeSerieExtractor()
    df_basket = ext.fetch_market_basket(ventana_anios=VENTANA_ANIOS_GANADORA)
    logger.info(f"Dataset de producción (ventana {VENTANA_ANIOS_GANADORA} años): {len(df_basket):,} líneas.")

    reglas = construir_item_item(df_basket, top_k_vecinos=TOP_K_VECINOS_GANADOR)
    if reglas is None or reglas.empty:
        raise RuntimeError("construir_item_item no generó relaciones -- no se publica el artefacto.")

    fecha_min = str(df_basket["fecha"].min())
    fecha_max = str(df_basket["fecha"].max())

    save_recommendation_rules(
        reglas,
        algorithm=f"filtrado colaborativo item-item (similitud coseno, top_k={TOP_K_VECINOS_GANADOR}, ventana={VENTANA_ANIOS_GANADORA} años)",
        contract_version="0.2.0",
        metrics={**METRICAS_BACKTEST_GANADOR, "n_reglas": len(reglas)},
        data_range={
            "ventana_anios": VENTANA_ANIOS_GANADORA,
            "fecha_min_entrenamiento": fecha_min,
            "fecha_max_entrenamiento": fecha_max,
            "n_lineas_entrenamiento": len(df_basket),
        },
        extra={
            "problema": "venta_cruzada_top_n",
            "clave_producto": "codart",
            "top_k_vecinos": TOP_K_VECINOS_GANADOR,
            "ganador_backtest": "item_item sobre coocurrencia/apriori_mlxtend/hibrido -- ver ml/REPORTE_MEJORA_MODELOS.md",
        },
    )
    logger.info("Artefacto ganador publicado en models/recommendation.pkl (+ sidecar .meta.json).")


if __name__ == "__main__":
    main()
