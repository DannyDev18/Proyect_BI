# backend/app/services/goals_service.py
"""Extraído de `GoalsAutomationService` (antes en `analytics_service.py`). Metas y
Comisiones ya no usa ningún modelo ML (`goals_rf` fue decomisionado, ver
docs/auditoria/20_...md): la meta oficial se calcula con estadística pura
(`IQRGoalCalculationEngine` vía `GoalMLService`, sobre Venta Neta). Este servicio queda
solo para operaciones CRUD/consulta simples sobre `metas_comerciales_operativas`."""
import datetime
import logging

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.models.goal import Goal
from app.repositories.catalog_repository import CatalogRepository
from app.repositories.goal_repository import GoalRepository

logger = logging.getLogger("Backend.GoalsService")


class GoalsService:
    def __init__(self, goal_repo: GoalRepository, catalog_repo: CatalogRepository | None = None):
        self.goal_repo = goal_repo
        self.catalog_repo = catalog_repo

    def get_periods(self) -> list[dict[str, int]]:
        """El selector "Año / Mes de Planificación" de la Consola de Metas antes solo
        ofrecía el mes vigente y el siguiente (quemado en código) -- gerencia no podía
        planificar más de un mes por adelantado. Ahora se generan automáticamente los
        próximos `GOALS_HORIZONTE_PLANIFICACION_MESES` meses calendario a partir del mes
        vigente (configurable por env, nunca un número fijo en el código), además de
        cualquier período histórico que ya tenga metas generadas en
        `metas_comerciales_operativas`."""
        latest = self.goal_repo.get_latest_edw_period()
        if latest:
            current_year, current_month = latest
        else:
            now = datetime.datetime.now()
            current_year, current_month = now.year, now.month

        periods = self.goal_repo.get_periods_with_data()
        existentes = {(p["anio"], p["mes"]) for p in periods}

        anio, mes = current_year, current_month
        for _ in range(settings.GOALS_HORIZONTE_PLANIFICACION_MESES + 1):
            if (anio, mes) not in existentes:
                periods.append({"anio": anio, "mes": mes})
                existentes.add((anio, mes))
            mes += 1
            if mes > 12:
                mes = 1
                anio += 1

        periods.sort(key=lambda x: (x["anio"], x["mes"]))
        return periods

    def get_commission_tracking(self, anio: int, mes: int, vendedor: str | None = None) -> list[dict]:
        """`activo` (petición explícita del usuario, ampliada: la Consola de Metas debe
        listar SOLO vendedores activos -- `edw.dim_vendedor.activo`, enriquecido en lote,
        nunca N+1). Un vendedor dado de baja puede conservar una propuesta `PROPUESTA`
        pendiente de revisión (generada antes de la baja); antes se mostraba con un
        badge "Inactivo" para que gerencia decidiera, ahora se filtra por completo de la
        consola -- no tiene sentido aprobar/gestionar la meta de alguien que ya no
        vende."""
        filas = self.goal_repo.get_commission_report(anio, mes, vendedor=vendedor)
        if self.catalog_repo is not None and filas:
            activos = self.catalog_repo.get_vendedores_activo_bulk([f["vendedor_origen"] for f in filas])
            for f in filas:
                f["activo"] = activos.get(f["vendedor_origen"], False)
            filas = [f for f in filas if f["activo"]]
        else:
            for f in filas:
                f["activo"] = True
        return filas

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
