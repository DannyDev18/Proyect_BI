# backend/tests/unit/test_goals_service.py
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import NotFoundError
from app.repositories.goal_repository import VendorSalesTrend
from app.services.goals_service import GROWTH_RATIO_MAX, GROWTH_RATIO_MIN, GoalsService


@pytest.fixture
def goal_repo():
    return MagicMock()


def test_review_goal_lanza_not_found_si_no_existe(goal_repo, fake_model_loader):
    goal_repo.get_by_id.return_value = None
    service = GoalsService(goal_repo, fake_model_loader)

    with pytest.raises(NotFoundError):
        service.review_goal(goal_id=999, estado="APROBADA", approved_by_user_id=1)


def test_review_goal_delega_actualizacion_al_repositorio(goal_repo, fake_model_loader):
    goal = MagicMock()
    goal_repo.get_by_id.return_value = goal
    goal_repo.update_review.return_value = goal
    service = GoalsService(goal_repo, fake_model_loader)

    result = service.review_goal(goal_id=1, estado="APROBADA", approved_by_user_id=7, monto_meta=1000.0)

    assert result is goal
    goal_repo.update_review.assert_called_once_with(goal, "APROBADA", 7, 1000.0, None)


def test_predict_goal_amount_usa_fallback_heuristico_sin_modelo(goal_repo):
    from app.ml.model_loader import ModelLoader
    empty_loader = ModelLoader(models_dir="/nonexistent")  # sin modelos cargados
    service = GoalsService(goal_repo, empty_loader)

    trend = VendorSalesTrend(
        vendedor_origen="V1", sucursal="Quito", ventas_anterior=1000.0, unidades_anterior=10.0,
        ventas_anio_anterior=900.0, promedio_movil_3m=950.0, vendedor_sk=1, sucursal_sk=1,
    )
    monto = service._predict_goal_amount(trend, anio_ant=2025, mes_ant=6, factor_presion=1.1)

    assert monto == pytest.approx(1000.0 * 1.1)


def test_predict_goal_amount_aplica_capping_al_growth_ratio(goal_repo):
    """El modelo dummy predice 42.0 -- debe quedar acotado a GROWTH_RATIO_MAX."""
    from app.ml.model_loader import ModelLoader
    import numpy as np

    class DummyModel:
        feature_names_in_ = np.array(["anio", "mes", "ventas_historicas", "unidades_historicas", "ventas_anio_anterior", "promedio_movil_3m"])
        def predict(self, X):
            return np.array([42.0])

    loader = ModelLoader(models_dir="/nonexistent")
    loader._models = {"goals_rf": DummyModel()}
    service = GoalsService(goal_repo, loader)

    trend = VendorSalesTrend(
        vendedor_origen="V1", sucursal="Quito", ventas_anterior=1000.0, unidades_anterior=10.0,
        ventas_anio_anterior=900.0, promedio_movil_3m=950.0, vendedor_sk=1, sucursal_sk=1,
    )
    monto = service._predict_goal_amount(trend, anio_ant=2025, mes_ant=6, factor_presion=1.0)

    # Con growth_ratio acotado a GROWTH_RATIO_MAX=1.2, el monto no debe explotar
    # descontroladamente por la predicción cruda de 42.0.
    assert monto < 1000.0 * GROWTH_RATIO_MAX * 2
    assert GROWTH_RATIO_MIN <= 1.2 <= GROWTH_RATIO_MAX
