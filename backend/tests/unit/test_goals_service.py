# backend/tests/unit/test_goals_service.py
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import NotFoundError
from app.services.goals_service import GoalsService


@pytest.fixture
def goal_repo():
    return MagicMock()


def test_review_goal_lanza_not_found_si_no_existe(goal_repo):
    goal_repo.get_by_id.return_value = None
    service = GoalsService(goal_repo)

    with pytest.raises(NotFoundError):
        service.review_goal(goal_id=999, estado="APROBADA", approved_by_user_id=1)


def test_review_goal_delega_actualizacion_al_repositorio(goal_repo):
    goal = MagicMock()
    goal_repo.get_by_id.return_value = goal
    goal_repo.update_review.return_value = goal
    service = GoalsService(goal_repo)

    result = service.review_goal(goal_id=1, estado="APROBADA", approved_by_user_id=7, monto_meta=1000.0)

    assert result is goal
    goal_repo.update_review.assert_called_once_with(goal, "APROBADA", 7, 1000.0, None)
