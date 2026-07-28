"""Test de guardia del registro de modelos (Fase 1, docs/features/plan_mejora_pipeline_ml.md §3).

Falla si:
1. `ml/models/registry.json` no existe o no es un JSON válido.
2. Un `.pkl` en la raíz de `ml/models/` (los archivos campeón vigentes, NO
   `versions/`) no está referenciado como `champion` de ninguna clave del
   registro -- artefacto huérfano, exactamente el problema D-6 del plan
   ("conviven artefactos legacy... sin que nada indique cuál es el vigente").
3. Un `champion` declarado en el registro no tiene su `.pkl` en disco.

No valida los legacy movidos a `versions/_legacy/`: esos ya no compiten por
ser "el campeón", están archivados a propósito.

Ejecutar desde `ml/`: pytest tests/test_registry.py -v
"""
from __future__ import annotations

import json
import os
from pathlib import Path

MODELS_DIR = Path(os.getenv("ML_MODELS_DIR", str(Path(__file__).resolve().parent.parent / "models")))
REGISTRY_PATH = MODELS_DIR / "registry.json"


def _load_registry() -> dict:
    assert REGISTRY_PATH.exists(), f"No existe {REGISTRY_PATH} -- Fase 1 del plan requiere el registro."
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_registry_es_json_valido():
    registry = _load_registry()
    assert isinstance(registry, dict) and registry, "registry.json debe ser un objeto no vacío."
    for key, entry in registry.items():
        assert "champion" in entry, f"'{key}' no declara 'champion' en registry.json."
        assert entry["champion"].endswith(".pkl"), f"'{key}'.champion debe ser un archivo .pkl."


def test_ningun_pkl_en_raiz_es_huerfano():
    registry = _load_registry()
    campeones_declarados = {entry["champion"] for entry in registry.values()}
    pkls_en_raiz = {p.name for p in MODELS_DIR.glob("*.pkl")}
    huerfanos = pkls_en_raiz - campeones_declarados
    assert not huerfanos, (
        f"Artefactos en ml/models/ (raíz) sin referencia en registry.json: {sorted(huerfanos)}. "
        "Muévelos a ml/models/versions/_legacy/ o agrégalos al registro."
    )


def test_todo_campeon_declarado_existe_en_disco():
    registry = _load_registry()
    faltantes = [
        (key, entry["champion"])
        for key, entry in registry.items()
        if not (MODELS_DIR / entry["champion"]).exists()
    ]
    assert not faltantes, f"Campeones declarados en registry.json sin .pkl en disco: {faltantes}"
