# backend/app/services/goals_service.py
"""Extraído de `GoalsAutomationService` (antes en `analytics_service.py`). Metas y
Comisiones ya no usa ningún modelo ML (`goals_rf` fue decomisionado, ver
docs/auditoria/20_...md): la meta oficial se calcula con estadística pura
(`IQRGoalCalculationEngine` vía `GoalMLService`, sobre Venta Neta). Este servicio queda
solo para operaciones CRUD/consulta simples sobre `metas_comerciales_operativas`."""
import datetime
import logging

from app.core.exceptions import NotFoundError
from app.models.goal import Goal
from app.repositories.goal_repository import GoalRepository

logger = logging.getLogger("Backend.GoalsService")


class GoalsService:
    def __init__(self, goal_repo: GoalRepository):
        self.goal_repo = goal_repo

    def get_periods(self) -> list[dict[str, int]]:
        latest = self.goal_repo.get_latest_edw_period()
        if latest:
            current_year, current_month = latest
        else:
            now = datetime.datetime.now()
            current_year, current_month = now.year, now.month

        next_month = current_month + 1 if current_month < 12 else 1
        next_month_year = current_year if current_month < 12 else current_year + 1

        periods = self.goal_repo.get_periods_with_data()
        if not any(p["anio"] == current_year and p["mes"] == current_month for p in periods):
            periods.insert(0, {"anio": current_year, "mes": current_month})
        if not any(p["anio"] == next_month_year and p["mes"] == next_month for p in periods):
            periods.insert(0, {"anio": next_month_year, "mes": next_month})

        periods.sort(key=lambda x: (x["anio"], x["mes"]))
        return periods

    def get_commission_tracking(self, anio: int, mes: int) -> list[dict]:
        return self.goal_repo.get_commission_report(anio, mes)

    def review_goal(
        self, goal_id: int, estado: str, approved_by_user_id: int,
        monto_meta: float | None = None, comision_base_pct: float | None = None,
    ) -> Goal:
        """Reemplaza el acceso directo al ORM que antes vivía en el router
        `goals.py::review_goal` (violación de capas: el router hacía `db.query`/`commit`
        directamente)."""
        goal = self.goal_repo.get_by_id(goal_id)
        if not goal:
            raise NotFoundError(f"No se encontró la meta con ID {goal_id}.")
        return self.goal_repo.update_review(goal, estado, approved_by_user_id, monto_meta, comision_base_pct)
