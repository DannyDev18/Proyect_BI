"""Smoke test paramétrico de la capa de contratos ML.

Recorre `ml/contracts/models/*.json` y valida cada artefacto legacy en
`ml/models/` (o `ML_MODELS_DIR`) contra su contrato. Los 7 artefactos
actuales son legacy (entrenados antes de la capa de contratos y de la
reconstrucción sobre el EDW nuevo — ver docs/auditoria/11_auditoria_tecnica_modelos_ml.md):
se marcan `xfail` con referencia al hallazgo que los rompe, para que la
suite documente el estado conocido sin fallar en rojo. Cuando un modelo se
reconstruya (Fase 3, doc 12 §6) y su contrato pase a "active", el `xfail`
correspondiente debe eliminarse y el test debe pasar en modo estricto.

Ejecutar desde `ml/`: pytest tests/test_model_contract.py -v
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.contracts.contract_validator import resolve_models_dir, validate_artifact
from src.contracts.model_contract import ModelContract, contracts_dir

# Hallazgo (auditoría 11) que documenta por qué el .pkl legacy de cada
# modelo no puede pasar su contrato todavía.
LEGACY_XFAIL_REASON = {
    "sales": "H-01: predicción en escala log1p servida sin expm1",
    "demand": "H-01 + H-08: escala log1p + sin ventana de 3 años",
    "segmentation": "H-02: artefacto serializado como dict {model, scaler}, no como Pipeline",
    "churn": "H-03 + H-05: features de serving distintas a las de entrenamiento + etiqueta circular",
    "anomalies": "H-04: features de serving distintas a las de entrenamiento + score ficticio",
    "recommendation": "H-10: reglas sin confianza/lift, filtro asimétrico item_A/item_B",
    "goals": "H-13: 7 features en entrenamiento vs 6 en goals_service.py",
}

# Patrón de archivo legacy en ml/models/ para cada contrato (los nombres
# legacy no siempre coinciden con el nombre del contrato nuevo).
LEGACY_ARTIFACT_GLOB = {
    "sales": "sales*.pkl",
    "demand": "demand*.pkl",
    "segmentation": "kmeans_rfm_model.pkl",
    "churn": "churn*.pkl",
    "anomalies": "isolation_forest_model.pkl",
    "recommendation": "association_rules.pkl",
    "goals": "goals*.pkl",
}


def _load_contracts() -> list[ModelContract]:
    return [ModelContract.load(p) for p in sorted(contracts_dir().glob("*.json"))]


CONTRACTS = _load_contracts()


@pytest.mark.parametrize("contract", CONTRACTS, ids=lambda c: c.name)
def test_contract_is_well_formed(contract: ModelContract) -> None:
    """Todo contrato declarado en el repo debe ser sintácticamente válido — esto debe pasar siempre, incluso en draft."""
    assert contract.name
    assert contract.task
    assert contract.status in {"draft", "active"}


@pytest.mark.parametrize("contract", CONTRACTS, ids=lambda c: c.name)
def test_legacy_artifact_against_contract(contract: ModelContract) -> None:
    """Valida el .pkl/.meta.json legacy (si existe) contra el contrato.

    xfail documentado para los 7 artefactos legacy conocidos (auditoría 11).
    Si no hay .pkl en disco (entorno sin ml/models poblado), se hace skip.
    """
    models_dir = Path(resolve_models_dir())
    pattern = LEGACY_ARTIFACT_GLOB.get(contract.name, f"{contract.name}*.pkl")
    pkl_candidates = sorted(models_dir.glob(pattern)) if models_dir.exists() else []
    if not pkl_candidates:
        pytest.skip(f"no hay .pkl en {models_dir} para '{contract.name}' (entorno sin modelos)")

    reason = LEGACY_XFAIL_REASON.get(contract.name)
    if reason:
        pytest.xfail(reason)

    meta_path = pkl_candidates[0].with_suffix(".meta.json")
    result = validate_artifact(contract, meta_path)
    assert result.ok, result.describe()


def test_no_active_contract_without_features() -> None:
    """Ningún contrato debe quedar 'active' sin features declaradas: un contrato activo es un gate de publicación real, no un borrador."""
    for contract in CONTRACTS:
        if contract.status == "active":
            assert contract.features.features, f"contrato '{contract.name}' está en status=active pero no declara features"
