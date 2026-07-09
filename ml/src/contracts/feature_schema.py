"""Esquema declarativo de features para los contratos ML.

Define `FeatureSpec` (una columna) y `FeatureSchema` (el conjunto ordenado de
columnas que un modelo espera), con comparación explícita contra las columnas
reales de un dataset de entrenamiento o de una fila de serving. Ver
docs/ml_contracts.md.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

_VALID_DTYPES = {"int", "float", "bool", "string", "datetime", "category"}


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    dtype: str
    required: bool = True
    nullable: bool = False
    description: str = ""

    def __post_init__(self) -> None:
        if self.dtype not in _VALID_DTYPES:
            raise ValueError(
                f"FeatureSpec({self.name!r}): dtype {self.dtype!r} inválido, "
                f"use uno de {sorted(_VALID_DTYPES)}"
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FeatureSpec":
        return cls(
            name=data["name"],
            dtype=data["dtype"],
            required=data.get("required", True),
            nullable=data.get("nullable", False),
            description=data.get("description", ""),
        )


@dataclass(frozen=True)
class FeatureDiff:
    missing: list[str]
    unexpected: list[str]
    order_mismatch: bool

    @property
    def ok(self) -> bool:
        return not self.missing and not self.order_mismatch

    def describe(self) -> str:
        parts = []
        if self.missing:
            parts.append(f"faltan columnas requeridas: {self.missing}")
        if self.order_mismatch:
            parts.append("el orden de columnas no coincide con el contrato")
        if self.unexpected:
            parts.append(f"columnas no declaradas en el contrato (informativo): {self.unexpected}")
        return "; ".join(parts) if parts else "esquema conforme"


@dataclass(frozen=True)
class FeatureSchema:
    """Conjunto ORDENADO de columnas que un modelo espera como entrada."""

    features: tuple[FeatureSpec, ...] = field(default_factory=tuple)

    @property
    def names(self) -> list[str]:
        return [f.name for f in self.features]

    @property
    def required_names(self) -> list[str]:
        return [f.name for f in self.features if f.required]

    def to_list(self) -> list[dict[str, Any]]:
        return [f.to_dict() for f in self.features]

    @classmethod
    def from_list(cls, data: Iterable[dict[str, Any]]) -> "FeatureSchema":
        return cls(features=tuple(FeatureSpec.from_dict(d) for d in data))

    def diff(self, columns: Iterable[str]) -> FeatureDiff:
        """Compara el schema contra las columnas reales de un DataFrame (o lista)."""
        actual = list(columns)
        actual_set = set(actual)
        missing = [n for n in self.required_names if n not in actual_set]
        expected_set = set(self.names)
        unexpected = [c for c in actual if c not in expected_set]
        order_mismatch = False
        if not missing:
            expected_order = [n for n in self.names if n in actual_set]
            actual_order = [c for c in actual if c in expected_set]
            order_mismatch = expected_order != actual_order
        return FeatureDiff(missing=missing, unexpected=unexpected, order_mismatch=order_mismatch)
