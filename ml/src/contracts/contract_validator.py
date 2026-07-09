"""Barrera de calidad de la capa de contratos ML.

`python -m src.contracts.contract_validator` (ejecutar desde `ml/`) recorre
`ml/contracts/models/*.json`, busca el `.pkl`/`.meta.json` correspondiente en
`ML_MODELS_DIR` y reporta si cada artefacto cumple su contrato. Debe correr
ANTES de `publish_models.py` (ver docs/ml_contracts.md): un contrato
`active` que falla bloquea la publicación; uno `draft` solo informa.

No importa nada de `backend/`: la compatibilidad con el serving se declara
en el JSON del contrato (`population_filter`, `known_serving_mismatch`), no
se verifica importando los repositorios del backend (riesgo R-4, auditoría
12 — dos imágenes Docker separadas).
"""
from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .artifact_schema import ArtifactMetadata
from .model_contract import ModelContract, load_all_contracts

logger = logging.getLogger("ML.ContractValidator")

MODELS_DIR_ENV = "ML_MODELS_DIR"
DEFAULT_MODELS_DIR = "./models"


def resolve_models_dir() -> str:
    return os.getenv(MODELS_DIR_ENV, DEFAULT_MODELS_DIR)


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def merge(self, other: "ValidationResult") -> "ValidationResult":
        return ValidationResult(ok=self.ok and other.ok, errors=self.errors + other.errors, warnings=self.warnings + other.warnings)

    def describe(self) -> str:
        lines = [f"  ERROR: {e}" for e in self.errors] + [f"  WARN:  {w}" for w in self.warnings]
        return "\n".join(lines) if lines else "  OK"


def validate_features(contract: ModelContract, columns: Iterable[str]) -> ValidationResult:
    """Compara columnas reales (dataset de entrenamiento o fila de serving) contra `contract.features`."""
    if not contract.features.features:
        return ValidationResult(ok=True, warnings=["contrato sin features declaradas (draft sin diseño de dataset aún)"])
    diff = contract.features.diff(columns)
    if diff.ok:
        warnings = [f"columnas no declaradas en el contrato: {diff.unexpected}"] if diff.unexpected else []
        return ValidationResult(ok=True, warnings=warnings)
    return ValidationResult(ok=False, errors=[diff.describe()])


def validate_artifact(contract: ModelContract, meta_path: str | Path) -> ValidationResult:
    """Valida el sidecar `.meta.json` de un artefacto contra el contrato."""
    meta_path = Path(meta_path)
    if not meta_path.exists():
        if contract.is_active:
            return ValidationResult(ok=False, errors=[f"contrato ACTIVE sin sidecar de metadata: {meta_path}"])
        return ValidationResult(ok=True, warnings=[f"no existe {meta_path.name}: artefacto legacy sin metadata (permitido en draft)"])

    with open(meta_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    try:
        meta = ArtifactMetadata.from_dict(raw)
    except ValueError as exc:
        return ValidationResult(ok=False, errors=[str(exc)])

    result = validate_features(contract, meta.features)

    if contract.is_active:
        if meta.is_legacy:
            result = result.merge(
                ValidationResult(
                    ok=False,
                    errors=[
                        "contrato ACTIVE pero el artefacto no tiene metadata de Fase 1 "
                        "(contract_name/library_versions) — parece un .pkl legacy, no reentrenado"
                    ],
                )
            )
        if contract.target.transform and meta.target_transform != contract.target.transform:
            result = result.merge(
                ValidationResult(
                    ok=False,
                    errors=[
                        f"target.transform del contrato ({contract.target.transform!r}) no coincide con "
                        f"el sidecar ({meta.target_transform!r}) — riesgo de bug de escala (H-01)"
                    ],
                )
            )
    else:
        result = result.merge(ValidationResult(ok=True, warnings=["contrato en estado draft: no bloquea publicación"]))

    return result


def validate_prediction(contract: ModelContract, value: float) -> ValidationResult:
    """Valida que una predicción esté en el rango plausible declarado por el contrato.

    Es la barrera que convierte el bug de escala log1p (H-01: venta diaria de
    "12.3 USD" en vez de "~160.000 USD") en un fallo explícito en vez de un
    número silenciosamente incorrecto en el dashboard.
    """
    rng = contract.output.plausible_range
    if rng is None:
        return ValidationResult(ok=True, warnings=["contrato sin plausible_range declarado: no se puede validar escala"])
    low, high = rng
    if low <= value <= high:
        return ValidationResult(ok=True)
    return ValidationResult(
        ok=False,
        errors=[f"predicción {value} fuera del rango plausible [{low}, {high}] declarado en output.plausible_range — posible bug de escala/transform"],
    )


def _artifact_paths_for(contract: ModelContract) -> tuple[Path, Path]:
    models_dir = Path(resolve_models_dir())
    return models_dir / f"{contract.name}.pkl", models_dir / f"{contract.name}.meta.json"


def run_report(contracts: dict[str, ModelContract] | None = None) -> bool:
    """Recorre todos los contratos y reporta su estado.

    Devuelve True si ningún contrato ACTIVE tiene errores (gate de publicación).
    """
    contracts = contracts or load_all_contracts()
    all_ok = True
    print(f"=== Validación de contratos ML ({len(contracts)} contratos) ===\n")
    for name, contract in sorted(contracts.items()):
        pkl_path, meta_path = _artifact_paths_for(contract)
        print(f"[{contract.status.upper():6}] {name} (v{contract.version}, task={contract.task})")
        if not pkl_path.exists():
            print(f"  WARN:  no existe artefacto {pkl_path.name} (aún no reconstruido)")
            if contract.is_active:
                all_ok = False
            continue
        result = validate_artifact(contract, meta_path)
        print(result.describe())
        if contract.is_active and not result.ok:
            all_ok = False
    print(f"\n=== {'PASA' if all_ok else 'FALLA'} (gate de publicación) ===")
    return all_ok


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(0 if run_report() else 1)
