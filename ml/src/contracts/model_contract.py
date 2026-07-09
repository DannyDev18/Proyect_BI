"""Contrato declarativo de un modelo ML: la especificación que un artefacto
`.pkl` debe cumplir para poder publicarse hacia el backend.

Regla D-2 (auditoría 12, docs/auditoria/12_fase0_analisis_capa_contratos_ml.md):
el contrato se escribe ANTES del entrenamiento, a partir del diseño esperado
del pipeline y las reglas de negocio del EDW — nunca se deriva de un `.pkl`
existente ni de `feature_names_in_`. Ver docs/ml_contracts.md.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .feature_schema import FeatureSchema

VALID_TASKS = {
    "regression",
    "classification",
    "clustering",
    "recommendation",
    "anomaly_detection",
}
VALID_STATUS = {"draft", "active"}


@dataclass(frozen=True)
class TargetSpec:
    name: str = ""
    transform: str | None = None
    inverse_transform: str | None = None
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "TargetSpec":
        data = data or {}
        return cls(
            name=data.get("name", ""),
            transform=data.get("transform"),
            inverse_transform=data.get("inverse_transform"),
            description=data.get("description", ""),
        )


@dataclass(frozen=True)
class OutputSpec:
    type: str = "float"
    unit: str = ""
    plausible_range: tuple[float, float] | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["plausible_range"] = list(self.plausible_range) if self.plausible_range is not None else None
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "OutputSpec":
        data = data or {}
        rng = data.get("plausible_range")
        return cls(
            type=data.get("type", "float"),
            unit=data.get("unit", ""),
            plausible_range=tuple(rng) if rng else None,
        )


@dataclass(frozen=True)
class PopulationFilter:
    description: str = ""
    sql_condition: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PopulationFilter":
        data = data or {}
        return cls(description=data.get("description", ""), sql_condition=data.get("sql_condition", ""))


@dataclass
class ModelContract:
    name: str
    version: str
    task: str
    status: str = "draft"
    features: FeatureSchema = field(default_factory=FeatureSchema)
    target: TargetSpec = field(default_factory=TargetSpec)
    output: OutputSpec = field(default_factory=OutputSpec)
    population_filter: PopulationFilter = field(default_factory=PopulationFilter)
    library_versions: dict[str, str] = field(default_factory=dict)
    data_range: dict[str, str] = field(default_factory=dict)
    known_serving_mismatch: list[str] = field(default_factory=list)
    notes: str = ""

    def __post_init__(self) -> None:
        if self.task not in VALID_TASKS:
            raise ValueError(f"ModelContract({self.name!r}): task {self.task!r} inválido, use uno de {sorted(VALID_TASKS)}")
        if self.status not in VALID_STATUS:
            raise ValueError(f"ModelContract({self.name!r}): status {self.status!r} inválido, use uno de {sorted(VALID_STATUS)}")

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "task": self.task,
            "status": self.status,
            "features": self.features.to_list(),
            "target": self.target.to_dict(),
            "output": self.output.to_dict(),
            "population_filter": self.population_filter.to_dict(),
            "library_versions": self.library_versions,
            "data_range": self.data_range,
            "known_serving_mismatch": self.known_serving_mismatch,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelContract":
        return cls(
            name=data["name"],
            version=data.get("version", "0.1.0"),
            task=data["task"],
            status=data.get("status", "draft"),
            features=FeatureSchema.from_list(data.get("features", [])),
            target=TargetSpec.from_dict(data.get("target")),
            output=OutputSpec.from_dict(data.get("output")),
            population_filter=PopulationFilter.from_dict(data.get("population_filter")),
            library_versions=data.get("library_versions", {}),
            data_range=data.get("data_range", {}),
            known_serving_mismatch=data.get("known_serving_mismatch", []),
            notes=data.get("notes", ""),
        )

    @classmethod
    def load(cls, path: str | Path) -> "ModelContract":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    def save(self, path: str | Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)


def contracts_dir() -> Path:
    """Directorio de contratos declarativos: ml/contracts/models/."""
    return Path(__file__).resolve().parents[2] / "contracts" / "models"


def load_all_contracts() -> dict[str, ModelContract]:
    return {c.name: c for c in (ModelContract.load(p) for p in sorted(contracts_dir().glob("*.json")))}
