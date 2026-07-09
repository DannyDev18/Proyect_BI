"""Esquema del sidecar `.meta.json` que acompaña a cada `.pkl` — superset
retrocompatible del formato que escribe hoy `ml/src/utils/model_export.py`.

Campos legacy (siempre presentes, formato actual): `model_file`, `algorithm`,
`features`, `metrics`, `trained_at`, `version`.
Campos nuevos de Fase 1 (opcionales — ausentes en artefactos legacy, ver
docs/auditoria/12_fase0_analisis_capa_contratos_ml.md §4.1): `contract_name`,
`contract_version`, `library_versions`, `data_range`, `population_filter`,
`target_transform`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

LEGACY_REQUIRED_KEYS = {"model_file", "algorithm", "features", "metrics", "trained_at", "version"}


@dataclass
class ArtifactMetadata:
    model_file: str
    algorithm: str
    features: list[str]
    metrics: dict[str, float]
    trained_at: str
    version: str
    contract_name: str | None = None
    contract_version: str | None = None
    library_versions: dict[str, str] = field(default_factory=dict)
    data_range: dict[str, str] = field(default_factory=dict)
    population_filter: str | None = None
    target_transform: str | None = None

    @property
    def is_legacy(self) -> bool:
        """True si el sidecar no tiene ningún campo de Fase 1 (artefacto pre-contratos)."""
        return self.contract_name is None and not self.library_versions

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArtifactMetadata":
        missing = LEGACY_REQUIRED_KEYS - data.keys()
        if missing:
            raise ValueError(f"meta.json inválido: faltan claves {sorted(missing)}")
        return cls(
            model_file=data["model_file"],
            algorithm=data["algorithm"],
            features=list(data.get("features", [])),
            metrics=dict(data.get("metrics", {})),
            trained_at=data["trained_at"],
            version=data["version"],
            contract_name=data.get("contract_name"),
            contract_version=data.get("contract_version"),
            library_versions=data.get("library_versions", {}),
            data_range=data.get("data_range", {}),
            population_filter=data.get("population_filter"),
            target_transform=data.get("target_transform"),
        )
