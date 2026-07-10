# backend/app/ml/contract_validation.py
"""Barrera de validación de contratos ML del lado del serving (backend).

`ml/src/contracts/contract_validator.py` es la barrera del lado del ENTRENAMIENTO
(`ml/`, otra imagen Docker) y no es importable desde aquí -- el backend de producción
no tiene acceso al código fuente de `ml/` (solo a los artefactos `.pkl` vía volumen de
solo lectura, ver docker-compose.yml y CLAUDE.md). La interfaz declarada entre ambos
lados es el JSON del contrato (`ml/contracts/models/<name>.json`), no las clases Python
de `ml/src/contracts/` -- por eso este módulo relee el mismo JSON con un parser propio,
mínimo y sin dependencias del paquete `ml.*` (misma decisión R-4 de la auditoría 12,
aplicada en sentido inverso).

Implementa el mismo concepto que `validate_features`/`validate_prediction` del lado de
entrenamiento, pero como una segunda barrera independiente del lado del serving: un
modelo puede pasar la validación en `ml/` al publicarse y aun así recibir, en producción,
una fila de features mal construida por el backend (bug de `preprocessing.py` o de un
repositorio) -- esta capa es la que atrapa ESE caso."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Iterable

from app.core.exceptions import ModelContractError

logger = logging.getLogger("Backend.ContractValidation")


@dataclass(frozen=True)
class ModelContractLite:
    """Subconjunto de `ml.src.contracts.model_contract.ModelContract` relevante para el
    serving: nombre, estado, columnas de entrada requeridas y rango plausible de salida.
    No se reutiliza la dataclass de `ml/` a propósito (ver docstring del módulo)."""
    name: str
    status: str
    required_features: tuple[str, ...]
    plausible_range: tuple[float, float] | None

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelContractLite":
        features = data.get("features", [])
        required = tuple(f["name"] for f in features if f.get("required", True))
        output = data.get("output", {}) or {}
        rng = output.get("plausible_range")
        return cls(
            name=data["name"],
            status=data.get("status", "draft"),
            required_features=required,
            plausible_range=tuple(rng) if rng else None,
        )


@dataclass
class ContractValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def load_contract(contracts_dir: str, name: str) -> ModelContractLite | None:
    """Lee `<contracts_dir>/<name>.json`. Devuelve `None` (con WARNING) si el directorio
    no está montado o el contrato no existe -- degradado tolerante, igual que
    `ModelLoader._load_meta_sidecar`, para no romper entornos donde el volumen de
    contratos todavía no se agregó (ver docker-compose.yml)."""
    path = os.path.join(contracts_dir, f"{name}.json")
    if not os.path.exists(path):
        logger.warning(f"Contrato '{name}' no encontrado en {path}. Validación de contrato omitida para este modelo.")
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return ModelContractLite.from_dict(json.load(f))
    except Exception as e:
        logger.warning(f"No se pudo leer/parsear el contrato '{name}' en {path}: {e}")
        return None


def validate_features(contract: ModelContractLite | None, columns: Iterable[str]) -> ContractValidationResult:
    if contract is None:
        return ContractValidationResult(ok=True, warnings=["sin contrato cargado: validación de features omitida"])
    actual = set(columns)
    missing = [c for c in contract.required_features if c not in actual]
    if missing:
        return ContractValidationResult(ok=False, errors=[f"faltan columnas requeridas por el contrato '{contract.name}': {missing}"])
    return ContractValidationResult(ok=True)


def validate_prediction(contract: ModelContractLite | None, value: float) -> ContractValidationResult:
    if contract is None or contract.plausible_range is None:
        return ContractValidationResult(ok=True, warnings=["contrato sin plausible_range: validación de escala omitida"])
    low, high = contract.plausible_range
    if low <= value <= high:
        return ContractValidationResult(ok=True)
    return ContractValidationResult(
        ok=False,
        errors=[f"predicción {value} fuera del rango plausible [{low}, {high}] del contrato '{contract.name}' -- posible bug de escala/transform"],
    )


def enforce(contract: ModelContractLite | None, result: ContractValidationResult, context: str) -> None:
    """Traduce un `ContractValidationResult` fallido en `ModelContractError` -- solo
    bloquea si el contrato está `active` (un contrato `draft`, o ausente, no bloquea la
    inferencia, igual que en `ml/src/contracts/contract_validator.py`)."""
    if result.ok:
        return
    if contract is not None and not contract.is_active:
        logger.warning(f"[{context}] contrato '{contract.name}' en estado '{contract.status}': no bloquea, solo informa. {result.errors}")
        return
    mensaje = f"[{context}] Falló la validación de contrato ML: {'; '.join(result.errors)}"
    logger.error(mensaje)
    raise ModelContractError(mensaje)
