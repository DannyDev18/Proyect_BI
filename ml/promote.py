# ml/promote.py
"""Promoción manual / rollback de un modelo a una versión archivada específica (Fase 3,
docs/features/plan_mejora_pipeline_ml.md §3.2 y §5.3). Usado para:

1. **Rollback**: volver al campeón de una corrida anterior sin reentrenar --
   `python promote.py --model demand_rf --to 20260710.211124`.
2. **Promoción manual**: forzar como campeón una versión archivada que el gating
   automático (`ml/src/training/promotion.py::evaluar_y_promover`) había rechazado, si un
   humano decide que sí vale la pena (p.ej. una métrica secundaria que el gate no captura).

A diferencia de `evaluar_y_promover` (que compara métricas y decide), este script no
evalúa nada: el humano ya decidió, aquí solo se aplica -- copia
`versions/<clave>/<version>.{pkl,meta.json}` sobre el archivo estable, actualiza
`registry.json` y deja traza en `public.ml_model_runs` con `disparado_por` explícito.

Uso: `python promote.py --model <clave> --to <version> --disparado-por <origen>`
Invocado por el backend (endpoints `POST /admin/modelos/promote` y `.../rollback`) vía
`docker compose run --rm ml python promote.py ...` (mismo mecanismo que `retrain_all.py`).
"""
import argparse
import json
import logging
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MLOps.Promote")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from src.training.promotion import (  # noqa: E402
    REPORTE_PATH, _models_dir, _leer_meta, _registrar_run, load_registry, save_registry,
)


def promover_version(clave: str, version_destino: str, disparado_por: str) -> dict:
    registry = load_registry()
    entry = registry.get(clave)
    if not entry:
        raise ValueError(f"'{clave}' no existe en registry.json.")

    champion_filename = entry["champion"]
    version_actual = entry.get("version")
    versions_dir = _models_dir() / "versions" / clave
    ext = Path(champion_filename).suffix
    origen_pkl = versions_dir / f"{version_destino}{ext}"
    origen_meta = versions_dir / f"{version_destino}.meta.json"
    if not origen_pkl.exists() or not origen_meta.exists():
        raise FileNotFoundError(f"No existe la versión '{version_destino}' de '{clave}' en {versions_dir}.")

    destino_pkl = _models_dir() / champion_filename
    destino_meta = _models_dir() / (Path(champion_filename).stem + ".meta.json")
    shutil.copy2(origen_pkl, destino_pkl)
    shutil.copy2(origen_meta, destino_meta)

    entry["version"] = version_destino
    registry[clave] = entry
    save_registry(registry)

    meta_nueva = _leer_meta(destino_meta) or {}
    meta_anterior = _leer_meta(versions_dir / f"{version_actual}.meta.json") if version_actual else None
    razon = f"Promoción manual/rollback: '{clave}' -> versión '{version_destino}' (disparado por {disparado_por})"
    metric_gate = entry.get("metric_gate")

    _registrar_run(
        clave, version_destino, version_actual, True, metric_gate,
        meta_nueva.get("metrics", {}), meta_anterior.get("metrics") if meta_anterior else None,
        razon, disparado_por,
    )
    with open(REPORTE_PATH, "a", encoding="utf-8") as f:
        f.write(f"\n- **{datetime.now(timezone.utc).isoformat()}** -- {razon}\n")

    logger.info(razon)
    return {"clave": clave, "version_anterior": version_actual, "version_nueva": version_destino}


def main() -> int:
    parser = argparse.ArgumentParser(description="Promueve/revierte un modelo a una versión archivada específica.")
    parser.add_argument("--model", required=True, help="Clave del modelo (registry.json).")
    parser.add_argument("--to", required=True, help="Versión destino (timestamp, ver ml/models/versions/<clave>/).")
    parser.add_argument("--disparado-por", default="manual", help="Origen del disparo (panel_admin_promote, panel_admin_rollback, cli).")
    args = parser.parse_args()
    try:
        resultado = promover_version(args.model, args.to, args.disparado_por)
        print(json.dumps(resultado))
        return 0
    except (ValueError, FileNotFoundError) as e:
        logger.error(str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
