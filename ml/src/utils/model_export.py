# ml/src/utils/model_export.py
"""Exportación única de artefactos ML: pkl (joblib) + sidecar de metadatos JSON.

Centraliza (DRY) el patrón que antes repetían las 7 funciones save_* de src/training:
os.makedirs + joblib.dump. Además escribe `<modelo>.meta.json` con la trazabilidad
mínima de MLOps: algoritmo ganador, features, métricas, fecha de entrenamiento y
versión. El backend puede leer el sidecar sin necesidad de deserializar el pkl.

Nota sobre ONNX: los ganadores de la competencia multi-algoritmo pueden ser XGBoost,
LightGBM o CatBoost (vía wrapper sklearn); su conversión a ONNX requiere onnxmltools y
no todos los tipos (p.ej. reglas de asociación en DataFrame) son convertibles, por lo
que el formato oficial de intercambio del proyecto es joblib. Ver
docs/auditoria/05_auditoria_ml_calidad_datos.md.
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import joblib

logger = logging.getLogger("ML.ModelExport")

MODELS_DIR_ENV = "ML_MODELS_DIR"
DEFAULT_MODELS_DIR = "./models"

RETENCION_VERSIONES_ENV = "ML_RETENCION_VERSIONES"
DEFAULT_RETENCION_VERSIONES = 5


def resolve_models_dir() -> str:
    return os.getenv(MODELS_DIR_ENV, DEFAULT_MODELS_DIR)


def save_artifact(
    obj: Any,
    filename: str,
    *,
    algorithm: str | None = None,
    features: list[str] | None = None,
    metrics: dict[str, float] | None = None,
    extra: dict[str, Any] | None = None,
    filepath: str | None = None,
    contract_name: str | None = None,
    contract_version: str | None = None,
    library_versions_used: dict[str, str] | None = None,
    data_range: dict[str, str] | None = None,
    population_filter: str | None = None,
    target_transform: str | None = None,
    registry_key: str | None = None,
) -> str:
    """Serializa `obj` con joblib y escribe `<stem>.meta.json` al lado.

    `filepath` explícito (tests / rutas custom) tiene prioridad sobre
    ML_MODELS_DIR/filename.

    Los parámetros `contract_name` en adelante son opcionales (Fase 1 de la
    capa de contratos, ver docs/ml_contracts.md); si se omiten, el sidecar
    queda idéntico al formato legacy — ningún call site existente en
    src/training/ necesita cambiar.

    `registry_key` (Fase 1 de `docs/features/plan_mejora_pipeline_ml.md`, §3.2):
    si se indica, además del archivo estable de siempre (`models_dir/filename`,
    el que el volumen Docker `:ro` expone al backend y que `registry.json`
    apunta como campeón), se guarda una copia versionada en
    `models_dir/versions/<registry_key>/<version>.{pkl,meta.json}`. El
    entrenamiento NUNCA sobrescribe el campeón vigente por sí solo más allá de
    seguir escribiendo el archivo estable (compatibilidad con el flujo manual
    actual); la promoción real de una versión a campeón la hace `registry.json`
    (Fase 3, `ml/src/training/promotion.py`), no este export. Retención de las
    últimas `ML_RETENCION_VERSIONES` (default 5) versiones por clave.
    """
    if filepath is None:
        filepath = os.path.join(resolve_models_dir(), filename)
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

    joblib.dump(obj, filepath)

    trained_at = datetime.now(timezone.utc)
    metadata: dict[str, Any] = {
        "model_file": os.path.basename(filepath),
        "algorithm": algorithm or type(obj).__name__,
        "features": features or _infer_features(obj),
        "metrics": {k: round(float(v), 6) for k, v in (metrics or {}).items()},
        "trained_at": trained_at.isoformat(),
        "version": trained_at.strftime("%Y%m%d.%H%M%S"),
    }
    if contract_name is not None:
        metadata["contract_name"] = contract_name
    if contract_version is not None:
        metadata["contract_version"] = contract_version
    if library_versions_used is not None:
        metadata["library_versions"] = library_versions_used
    if data_range is not None:
        metadata["data_range"] = data_range
    if population_filter is not None:
        metadata["population_filter"] = population_filter
    if target_transform is not None:
        metadata["target_transform"] = target_transform
    if extra:
        metadata.update(extra)

    meta_path = os.path.splitext(filepath)[0] + ".meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    logger.info(f"Artefacto guardado en {filepath} (metadatos: {os.path.basename(meta_path)})")

    if registry_key:
        _save_version_snapshot(filepath, meta_path, registry_key, metadata["version"])

    return filepath


def _save_version_snapshot(filepath: str, meta_path: str, registry_key: str, version: str) -> None:
    """Copia el par `.pkl`/`.meta.json` recién escrito a `versions/<registry_key>/<version>.*`
    y aplica retención (`ML_RETENCION_VERSIONES`). No toca `registry.json` -- ese puntero solo
    lo mueve la promoción (Fase 3), nunca el entrenamiento."""
    import shutil

    versions_dir = os.path.join(resolve_models_dir(), "versions", registry_key)
    os.makedirs(versions_dir, exist_ok=True)

    ext = os.path.splitext(filepath)[1]
    version_pkl = os.path.join(versions_dir, f"{version}{ext}")
    version_meta = os.path.join(versions_dir, f"{version}.meta.json")
    shutil.copy2(filepath, version_pkl)
    shutil.copy2(meta_path, version_meta)
    logger.info(f"Versión '{version}' de '{registry_key}' archivada en {versions_dir}.")

    retencion = int(os.getenv(RETENCION_VERSIONES_ENV, str(DEFAULT_RETENCION_VERSIONES)))
    # Bug corregido (encontrado en Fase 3 al probar el gating, docs/features/
    # plan_mejora_pipeline_ml.md): `os.path.splitext` solo quita la ÚLTIMA extensión, así
    # que para "<version>.meta.json" el "stem" salía "<version>.meta" -- distinto del
    # "<version>" que produce el .pkl del MISMO archivo versionado. El set de "stems"
    # quedaba con el doble de entradas de las reales (una por .pkl, otra por .meta.json),
    # lo que desalineaba el corte de retención y podía borrar un lado del par dejando el
    # otro huérfano (visto en vivo: un .meta.json sobrevivió sin su .pkl). Se normaliza
    # quitando ".meta.json" explícitamente antes de aplicar splitext.
    def _version_stem(nombre: str) -> str:
        if nombre.endswith(".meta.json"):
            return nombre[: -len(".meta.json")]
        return os.path.splitext(nombre)[0]

    stems = sorted({_version_stem(f) for f in os.listdir(versions_dir) if not f.startswith(".")})
    obsoletos = stems[:-retencion] if retencion > 0 and len(stems) > retencion else []
    for stem in obsoletos:
        for candidate in os.listdir(versions_dir):
            if _version_stem(candidate) == stem:
                os.remove(os.path.join(versions_dir, candidate))
        logger.info(f"Versión obsoleta '{stem}' de '{registry_key}' eliminada (retención={retencion}).")


def _infer_features(obj: Any) -> list[str]:
    """Features de entrenamiento si el estimador las expone (sklearn >= 1.0)."""
    names = getattr(obj, "feature_names_in_", None)
    if names is not None:
        return [str(n) for n in names]
    return []


def library_versions(*package_names: str) -> dict[str, str]:
    """Versiones instaladas de las librerías dadas (vía importlib.metadata).

    Pensado para poblar `library_versions_used` en `save_artifact`: los .pkl
    acoplan versiones de sklearn/xgboost/lightgbm/catboost entre ml/ y
    backend/ (H-20, auditoría 11), y hoy nada lo registra.
    """
    from importlib import metadata

    versions: dict[str, str] = {}
    for name in package_names:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
    return versions
