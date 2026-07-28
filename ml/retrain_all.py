# ml/retrain_all.py
"""Punto de entrada del reentrenamiento con gating (Fase 3,
docs/features/plan_mejora_pipeline_ml.md §5.1-5.2). Reemplaza el flujo roto de
`TrainingService` (docs/features/plan_mejora_pipeline_ml.md, corregido en la misma Fase 3):
el backend disparaba `python <script>.py` sobre cada archivo de `ml/src/training/`, pero
esos módulos solo DEFINEN funciones -- ninguno tenía un bloque `__main__`, así que el
"reentrenamiento" no entrenaba nada, solo importaba módulos y salía con éxito.

Este script SÍ entrena (llama a la función `train_*` real de `ml/main.py`) y, tras
guardar, evalúa el gating (`ml/src/training/promotion.py`) contra el campeón vigente de
`ml/models/registry.json` -- promueve solo si el candidato mejora o no degrada más del
`min_delta` configurado; si no, revierte el archivo estable a la versión anterior.

Uso:
    python retrain_all.py --model demand_rf
    python retrain_all.py --model all

Invocado por el backend (Vía A, panel de administración) vía
`docker compose run --rm ml python retrain_all.py --model <clave>` (contenedor `ml`
efímero, perfil `ml` -- ver TrainingService.trigger_retraining_pipeline)."""
import argparse
import logging
import sys

from main import (
    SalesTimeSerieExtractor,
    train_anomaly_detection,
    train_customer_churn,
    train_customer_segmentation,
    train_demand_forecasting,
    train_general_sales_prediction,
    train_recommendations,
)
from src.training.promotion import evaluar_y_promover

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MLOps.RetrainAll")

# Clave de registry.json -> función de entrenamiento en ml/main.py. Único punto de
# extensión si se agrega un modelo nuevo (mismo patrón que `_MODEL_FILES` en
# backend/app/ml/model_loader.py).
ENTRENADORES = {
    "sales_rf": train_general_sales_prediction,
    "demand_rf": train_demand_forecasting,
    "churn_rf": train_customer_churn,
    "segmentation": train_customer_segmentation,
    "association": train_recommendations,
    "anomaly": train_anomaly_detection,
}


def retrain_uno(clave: str, extractor: SalesTimeSerieExtractor, disparado_por: str) -> dict:
    entrenador = ENTRENADORES.get(clave)
    if entrenador is None:
        raise ValueError(f"Clave desconocida '{clave}'. Válidas: {sorted(ENTRENADORES)} o 'all'.")
    logger.info(f"=== Reentrenando '{clave}' con gating ===")
    entrenador(extractor)
    resultado = evaluar_y_promover(clave, disparado_por=disparado_por)
    logger.info(f"Resultado '{clave}': promovido={resultado['promovido']} -- {resultado['razon']}")
    return resultado


def main() -> int:
    parser = argparse.ArgumentParser(description="Reentrena uno o todos los modelos con gating de campeón único.")
    parser.add_argument("--model", required=True, choices=[*ENTRENADORES.keys(), "all"], help="Clave del modelo o 'all'.")
    parser.add_argument("--disparado-por", default="manual", help="Origen del disparo (panel_admin, cli, etc.) -- se guarda en public.ml_model_runs.")
    args = parser.parse_args()

    extractor = SalesTimeSerieExtractor()
    claves = list(ENTRENADORES.keys()) if args.model == "all" else [args.model]

    resultados = []
    fallo = False
    for clave in claves:
        try:
            resultados.append(retrain_uno(clave, extractor, args.disparado_por))
        except Exception as e:
            logger.error(f"Fallo entrenando '{clave}': {e}")
            fallo = True

    rechazados = [r["clave"] for r in resultados if not r["promovido"]]
    logger.info(f"=== Fin del reentrenamiento. Promovidos: {len(resultados) - len(rechazados)}/{len(resultados)}. Rechazados: {rechazados} ===")
    return 1 if fallo else 0


if __name__ == "__main__":
    sys.exit(main())
