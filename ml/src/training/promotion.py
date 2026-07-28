# ml/src/training/promotion.py
"""Gating de campeón único (Fase 3, docs/features/plan_mejora_pipeline_ml.md §5.1).

Corrige D-3 (docs/auditoria/38_mejora_pipeline_ml.md): hasta ahora cada reentrenamiento
sobrescribía el `.pkl` vigente sin comparar contra el anterior (así se degradó demanda de
R2=0.899 a 0.876 en un reentrenamiento sin que nada lo bloqueara). Este módulo se invoca
DESPUÉS de que la función `train_*` de `ml/main.py` ya entrenó y guardó (vía
`save_artifact(..., registry_key=...)`, Fase 1): guardar siempre escribe primero el archivo
estable (`models_dir/<filename>`, el que expone el volumen Docker al backend) y una copia
versionada en `models_dir/versions/<clave>/<version>.*`. `evaluar_y_promover` decide, ya con
ambos artefactos en disco, si esa sobreescritura se queda (promueve, actualiza
`registry.json`) o se revierte (restaura el `.pkl` del campeón anterior desde su copia
versionada) -- el entrenamiento nunca decide por sí solo si es mejor.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

from src.utils.model_export import resolve_models_dir

logger = logging.getLogger("ML.Promotion")

REGISTRY_FILENAME = "registry.json"
REPORTE_PATH = Path(__file__).resolve().parent.parent.parent / "REPORTE_MEJORA_MODELOS.md"


def _models_dir() -> Path:
    return Path(resolve_models_dir())


def _registry_path() -> Path:
    return _models_dir() / REGISTRY_FILENAME


def load_registry() -> dict[str, Any]:
    path = _registry_path()
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_registry(registry: dict[str, Any]) -> None:
    path = _registry_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _leer_meta(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def evaluar_gate(metric_gate: dict[str, Any], metrics_candidato: dict[str, float], metrics_campeon: dict[str, float]) -> tuple[bool, str]:
    """Compara candidato vs. campeón según `metric_gate` (ver `registry.json`).

    Convención unificada: se calcula una "mejora" con signo (positivo = mejor) sin
    importar si la métrica se maximiza o minimiza, y se promueve si `mejora >= min_delta`
    (un `min_delta` negativo tolera una pequeña degradación, tal como describe el plan:
    "promueve solo si el candidato mejora, o no degrada más de min_delta")."""
    nombre = metric_gate.get("name")
    direccion = metric_gate.get("direction")
    if nombre not in metrics_candidato or nombre not in metrics_campeon:
        return False, f"métrica '{nombre}' ausente en candidato o campeón -- no se promueve por seguridad"

    nuevo, viejo = float(metrics_candidato[nombre]), float(metrics_campeon[nombre])
    min_delta = float(metric_gate.get("min_delta", 0.0))

    if direccion == "maximize":
        mejora = nuevo - viejo
        ok = mejora >= min_delta
    elif direccion == "minimize":
        mejora = viejo - nuevo
        ok = mejora >= min_delta
    elif direccion == "target":
        target = float(metric_gate["target"])
        tolerancia = float(metric_gate.get("tolerance", 0.0))
        ok = abs(nuevo - target) <= abs(viejo - target) + tolerancia
    else:
        return False, f"dirección de gate desconocida: '{direccion}' -- no se promueve por seguridad"

    veredicto = "PROMUEVE" if ok else "RECHAZA"
    return ok, f"{veredicto} ({nombre}: candidato={nuevo:.4f} vs. campeón={viejo:.4f}, direction={direccion}, min_delta={min_delta})"


def _revertir_archivo_estable(clave: str, champion_filename: str, version_anterior: str) -> None:
    """Restaura `models_dir/<champion_filename>` desde la copia versionada del campeón
    anterior -- deshace la sobreescritura que `save_artifact` ya había hecho al entrenar."""
    versions_dir = _models_dir() / "versions" / clave
    ext = Path(champion_filename).suffix
    origen_pkl = versions_dir / f"{version_anterior}{ext}"
    origen_meta = versions_dir / f"{version_anterior}.meta.json"
    if not origen_pkl.exists() or not origen_meta.exists():
        logger.error(
            f"No se pudo revertir '{clave}': falta la versión archivada '{version_anterior}' en "
            f"{versions_dir}. El archivo estable QUEDA con el candidato rechazado -- revisar manualmente."
        )
        return
    destino_pkl = _models_dir() / champion_filename
    destino_meta = _models_dir() / (Path(champion_filename).stem + ".meta.json")
    shutil.copy2(origen_pkl, destino_pkl)
    shutil.copy2(origen_meta, destino_meta)
    logger.info(f"Archivo estable de '{clave}' revertido a la versión anterior '{version_anterior}'.")


def _registrar_run(
    clave: str, version_candidato: str, version_campeon_anterior: str | None, promovido: bool,
    metric_gate: dict[str, Any] | None, metrics_candidato: dict[str, float],
    metrics_campeon_anterior: dict[str, float] | None, razon: str, disparado_por: str,
) -> None:
    """Inserta una fila en `public.ml_model_runs` (misma base de datos Postgres que
    `edw.*`, otro esquema -- `ml/` y `backend/` son imágenes separadas pero comparten el
    mismo servidor Postgres, ver CLAUDE.md). Best-effort: si la tabla no existe todavía
    (migración 0004 no aplicada, o esquema `public` no accesible desde este entorno), se
    loguea un WARNING pero NO se aborta el entrenamiento -- el registro/versionado local
    (Fase 1) ya es la fuente de verdad operativa; esta tabla es solo trazabilidad."""
    pg_user = os.getenv("PG_USER", "etl_user")
    pg_password = os.getenv("PG_PASSWORD")
    pg_host = os.getenv("PG_HOST", "localhost")
    pg_port = os.getenv("PG_PORT", "5433")
    pg_db = os.getenv("PG_DB", "edw")
    if not pg_password:
        logger.warning("PG_PASSWORD no definida -- no se registra el run en public.ml_model_runs.")
        return

    metrica_nombre = metric_gate.get("name") if metric_gate else None
    try:
        engine = create_engine(f"postgresql+psycopg2://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_db}")
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO public.ml_model_runs
                        (clave, version_candidato, version_campeon_anterior, promovido,
                         metrica_nombre, metrica_candidato, metrica_campeon_anterior,
                         razon, metrics_candidato, metrics_campeon_anterior, disparado_por)
                    VALUES
                        (:clave, :version_candidato, :version_campeon_anterior, :promovido,
                         :metrica_nombre, :metrica_candidato, :metrica_campeon_anterior,
                         :razon, CAST(:metrics_candidato AS JSONB), CAST(:metrics_campeon_anterior AS JSONB), :disparado_por)
                """),
                {
                    "clave": clave,
                    "version_candidato": version_candidato,
                    "version_campeon_anterior": version_campeon_anterior,
                    "promovido": promovido,
                    "metrica_nombre": metrica_nombre,
                    "metrica_candidato": metrics_candidato.get(metrica_nombre) if metrica_nombre else None,
                    "metrica_campeon_anterior": (metrics_campeon_anterior or {}).get(metrica_nombre) if metrica_nombre else None,
                    "razon": razon,
                    "metrics_candidato": json.dumps(metrics_candidato),
                    "metrics_campeon_anterior": json.dumps(metrics_campeon_anterior) if metrics_campeon_anterior else None,
                    "disparado_por": disparado_por,
                },
            )
        logger.info(f"Run de '{clave}' registrado en public.ml_model_runs (promovido={promovido}).")
    except Exception as e:
        logger.warning(f"No se pudo registrar el run de '{clave}' en public.ml_model_runs: {e}")


def _append_reporte(clave: str, version_candidato: str, promovido: bool, razon: str) -> None:
    linea = (
        f"\n- **{datetime.now(timezone.utc).isoformat()}** -- gating de `{clave}` "
        f"(versión candidata `{version_candidato}`): {'PROMOVIDO' if promovido else 'RECHAZADO'}. {razon}\n"
    )
    with open(REPORTE_PATH, "a", encoding="utf-8") as f:
        f.write(linea)


def evaluar_y_promover(clave: str, disparado_por: str = "manual") -> dict[str, Any]:
    """Punto de entrada único, llamado por `ml/retrain_all.py` justo después de que la
    función `train_*` correspondiente ya entrenó y guardó (candidato ya escrito como
    archivo estable + versión archivada, Fase 1). Decide promover o revertir, registra el
    resultado, y devuelve un dict resumen (usado por `retrain_all.py` para el log de CLI y,
    en el futuro, por el endpoint `POST /admin/modelos/retrain` para el estado del job)."""
    registry = load_registry()
    entry = registry.get(clave)
    if not entry:
        return {
            "clave": clave, "promovido": False,
            "razon": f"'{clave}' no existe en registry.json -- no se puede evaluar el gate sin un campeón previo.",
        }

    champion_filename = entry["champion"]
    version_campeon_anterior = entry.get("version")
    metric_gate = entry.get("metric_gate")

    meta_estable_path = _models_dir() / (Path(champion_filename).stem + ".meta.json")
    meta_candidato = _leer_meta(meta_estable_path)
    if meta_candidato is None:
        return {"clave": clave, "promovido": False, "razon": f"No se encontró {meta_estable_path} tras entrenar."}
    version_candidato = meta_candidato["version"]
    metrics_candidato = meta_candidato.get("metrics", {})

    metrics_campeon_anterior = None
    if version_campeon_anterior:
        versions_dir = _models_dir() / "versions" / clave
        meta_campeon_path = versions_dir / f"{version_campeon_anterior}.meta.json"
        meta_campeon = _leer_meta(meta_campeon_path)
        metrics_campeon_anterior = meta_campeon.get("metrics", {}) if meta_campeon else None

    if not version_campeon_anterior or metrics_campeon_anterior is None or not metric_gate:
        # Primer registro real de este modelo (o snapshot anterior no encontrado): no hay
        # con qué comparar -- se promueve el candidato tal cual (mismo criterio que un
        # `registry.json` recién creado en Fase 1).
        promovido, razon = True, "sin campeón anterior comparable -- se promueve el candidato por defecto"
    else:
        promovido, razon = evaluar_gate(metric_gate, metrics_candidato, metrics_campeon_anterior)

    if promovido:
        entry["version"] = version_candidato
        registry[clave] = entry
        save_registry(registry)
    else:
        _revertir_archivo_estable(clave, champion_filename, version_campeon_anterior)

    _registrar_run(
        clave, version_candidato, version_campeon_anterior, promovido,
        metric_gate, metrics_candidato, metrics_campeon_anterior, razon, disparado_por,
    )
    _append_reporte(clave, version_candidato, promovido, razon)

    return {
        "clave": clave,
        "promovido": promovido,
        "razon": razon,
        "version_candidato": version_candidato,
        "version_campeon_anterior": version_campeon_anterior,
        "metrics_candidato": metrics_candidato,
        "metrics_campeon_anterior": metrics_campeon_anterior,
    }
