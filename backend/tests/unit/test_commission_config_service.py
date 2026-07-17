# backend/tests/unit/test_commission_config_service.py
"""Auditoría 34, H-9: `commission_engine._factor_credito` resuelve el primer rango de
crédito que matchea en el orden en que llega la lista -- si dos rangos configurados se
solapan, el resultado depende del orden de lectura de la BD en vez de una regla de
negocio explícita. `CommissionConfigService.replace_factores_credito` debe rechazar
rangos solapados antes de reemplazar la configuración vigente."""
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import ValidationError
from app.services.commission_config_service import CommissionConfigService


@pytest.fixture
def commission_config_repo():
    return MagicMock()


@pytest.fixture
def service(commission_config_repo):
    return CommissionConfigService(commission_config_repo, goal_repo=MagicMock(), catalog_repo=MagicMock())


def test_rangos_de_credito_sin_solape_se_aceptan(service, commission_config_repo):
    factores = [
        {"dias_desde": 0, "dias_hasta": 0, "factor": 1.0},
        {"dias_desde": 1, "dias_hasta": 30, "factor": 0.85},
        {"dias_desde": 31, "dias_hasta": None, "factor": 0.70},
    ]
    commission_config_repo.replace_factores_credito.return_value = []

    service.replace_factores_credito(factores)

    commission_config_repo.replace_factores_credito.assert_called_once_with(factores)


def test_rangos_de_credito_solapados_se_rechazan(service, commission_config_repo):
    factores = [
        {"dias_desde": 0, "dias_hasta": 30, "factor": 1.0},
        {"dias_desde": 15, "dias_hasta": 45, "factor": 0.85},  # se solapa 15-30
    ]

    with pytest.raises(ValidationError):
        service.replace_factores_credito(factores)

    commission_config_repo.replace_factores_credito.assert_not_called()


def test_rango_abierto_solapado_con_siguiente_se_rechaza(service, commission_config_repo):
    """Un rango sin `dias_hasta` (sin tope superior) se solapa con cualquier rango que
    empiece después de su `dias_desde`."""
    factores = [
        {"dias_desde": 0, "dias_hasta": None, "factor": 1.0},
        {"dias_desde": 30, "dias_hasta": 60, "factor": 0.85},
    ]

    with pytest.raises(ValidationError):
        service.replace_factores_credito(factores)


def test_rangos_contiguos_no_se_consideran_solapados(service, commission_config_repo):
    """Un rango que empieza exactamente donde termina el anterior + 1 día NO es
    solapamiento (0-30 seguido de 31-60 es la configuración esperada)."""
    factores = [
        {"dias_desde": 0, "dias_hasta": 30, "factor": 1.0},
        {"dias_desde": 31, "dias_hasta": 60, "factor": 0.85},
    ]
    commission_config_repo.replace_factores_credito.return_value = []

    service.replace_factores_credito(factores)

    commission_config_repo.replace_factores_credito.assert_called_once()
