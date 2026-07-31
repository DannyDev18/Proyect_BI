# backend/tests/unit/test_contract_validation.py
import json
import os

import pytest

from app.core.exceptions import ModelContractError
from app.ml.contract_validation import (
    ModelContractLite,
    enforce,
    load_contract,
    validate_features,
    validate_prediction,
)


def _write_contract(tmp_path, name: str, status: str = "active", plausible_range=(0, 100), features=None):
    features = features if features is not None else [
        {"name": "f1", "dtype": "float", "required": True},
        {"name": "f2", "dtype": "float", "required": True},
    ]
    contract = {
        "name": name,
        "version": "0.1.0",
        "task": "regression",
        "status": status,
        "features": features,
        "output": {"type": "float", "unit": "USD", "plausible_range": list(plausible_range) if plausible_range else None},
    }
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(contract), encoding="utf-8")
    return str(tmp_path)


def test_load_contract_devuelve_none_si_no_existe(tmp_path):
    assert load_contract(str(tmp_path), "inexistente") is None


def test_load_contract_parsea_correctamente(tmp_path):
    contracts_dir = _write_contract(tmp_path, "sales")
    contract = load_contract(contracts_dir, "sales")

    assert contract is not None
    assert contract.name == "sales"
    assert contract.is_active
    assert contract.required_features == ("f1", "f2")
    assert contract.plausible_range == (0.0, 100.0)


def test_validate_features_ok_sin_contrato():
    result = validate_features(None, ["a", "b"])
    assert result.ok


def test_validate_features_detecta_columnas_faltantes():
    contract = ModelContractLite(name="x", status="active", required_features=("a", "b"), plausible_range=None)
    result = validate_features(contract, ["a"])
    assert not result.ok
    assert "b" in result.errors[0]


def test_validate_prediction_dentro_de_rango():
    contract = ModelContractLite(name="x", status="active", required_features=(), plausible_range=(0.0, 10.0))
    assert validate_prediction(contract, 5.0).ok


def test_validate_prediction_fuera_de_rango():
    contract = ModelContractLite(name="x", status="active", required_features=(), plausible_range=(0.0, 10.0))
    result = validate_prediction(contract, 999.0)
    assert not result.ok
    assert "999.0" in result.errors[0]


def test_enforce_no_bloquea_si_contrato_es_draft():
    contract = ModelContractLite(name="x", status="draft", required_features=(), plausible_range=(0.0, 10.0))
    result = validate_prediction(contract, 999.0)
    enforce(contract, result, context="test")  # no debe lanzar


def test_enforce_bloquea_si_contrato_activo_falla():
    contract = ModelContractLite(name="x", status="active", required_features=(), plausible_range=(0.0, 10.0))
    result = validate_prediction(contract, 999.0)
    with pytest.raises(ModelContractError):
        enforce(contract, result, context="test")


def test_enforce_no_bloquea_sin_contrato():
    result = validate_features(None, ["cualquier_cosa"])
    enforce(None, result, context="test")  # no debe lanzar
