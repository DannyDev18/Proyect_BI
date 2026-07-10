# backend/app/services/goals_service.py
"""Extraído de `GoalsAutomationService` (antes en `analytics_service.py`). Las reglas de
capping/clamping son de negocio (no de acceso a datos ni de inferencia pura), así que
viven aquí; el SQL va a `GoalRepository` y la predicción del growth ratio a `app/ml/`."""
import datetime
import logging

import pandas as pd

from app.core.exceptions import NotFoundError
from app.ml import inference
from app.ml.model_loader import ModelLoader
from app.models.goal import Goal
from app.repositories.goal_repository import GoalRepository, VendorSalesTrend

logger = logging.getLogger("Backend.GoalsService")

# Límites de capping para evitar que una predicción del modelo (o su ausencia) genere
# metas irracionales frente al histórico reciente del vendedor.
GROWTH_RATIO_MIN, GROWTH_RATIO_MAX = 0.8, 1.2
META_VS_PROMEDIO_MOVIL_MIN, META_VS_PROMEDIO_MOVIL_MAX = 0.8, 1.2
META_VS_ANIO_ANTERIOR_MIN = 0.8


class GoalsService:
    def __init__(self, goal_repo: GoalRepository, model_loader: ModelLoader):
        self.goal_repo = goal_repo
        self.model_loader = model_loader

    def generate_proposals(self, anio: int, mes: int, factor_presion: float = 1.10) -> int:
        """Genera/actualiza propuestas de meta para el mes `anio`/`mes`, usando el mes
        anterior como base de predicción del growth ratio."""
        mes_ant = 12 if mes == 1 else mes - 1
        anio_ant = anio - 1 if mes == 1 else anio

        tendencias = self.goal_repo.get_sales_trend_for_goals(anio, mes)
        registros_afectados = 0

        for t in tendencias:
            meta_monto = self.predict_goal_amount(t, anio_ant, mes_ant, factor_presion)
            meta_unidades = max(0.0, float(t.unidades_anterior or 0.0) * factor_presion)

            existing = self.goal_repo.find_proposal(anio, mes, t.vendedor_origen, t.sucursal)
            if not existing:
                self.goal_repo.insert_proposal(anio, mes, t.vendedor_origen, t.sucursal, meta_monto, meta_unidades)
                registros_afectados += 1
            elif existing[1] == "PROPUESTA":
                self.goal_repo.update_proposal_amounts(existing[0], meta_monto, meta_unidades)
                registros_afectados += 1

        self.goal_repo.commit()
        return registros_afectados

    def predict_goal_amount(self, t: VendorSalesTrend, anio_ant: int, mes_ant: int, factor_presion: float) -> float:
        """Público (no `_privado`): reutilizado también por `GoalMLService` (integración
        Metas y Comisiones) para mostrar la meta sugerida por IA junto a la estadística,
        sin reimplementar el capping 0.8-1.2 aquí documentado."""
        ventas_ant = float(t.ventas_anterior or 0.0)
        mavg_3m = float(t.promedio_movil_3m or ventas_ant or 0.0)
        ventas_yoy = float(t.ventas_anio_anterior or 0.0)

        if not self.model_loader.is_loaded("goals_rf"):
            # Fallback heurístico si el modelo de metas no está disponible.
            return max(0.0, ventas_ant * factor_presion)

        # 6 features, igual que ml/contracts/models/goals.json (H-13, cerrado): 'anio' se
        # excluyó del entrenamiento (los árboles no extrapolan a años futuros) y se agregó
        # 'indice_estacional_relativo' (antes faltaba -- mismatch confirmado en auditoría 11).
        df_pred = pd.DataFrame([{
            "mes": mes_ant,
            "ventas_historicas": ventas_ant,
            "unidades_historicas": float(t.unidades_anterior or 0.0),
            "ventas_anio_anterior": ventas_yoy,
            "promedio_movil_3m": mavg_3m,
            "indice_estacional_relativo": float(t.indice_estacional_relativo or 1.0),
        }])
        growth_ratio = inference.predict_goal_growth_ratio(self.model_loader, df_pred)
        growth_ratio = max(GROWTH_RATIO_MIN, min(growth_ratio, GROWTH_RATIO_MAX))

        # Baseline con peso 50/50 entre venta del mes anterior y el promedio suavizado
        # (estacionalidad + tendencia sin pico) -- documentado en docs/features/feature_metas_comerciales.md.
        baseline = (ventas_ant * 0.5) + (mavg_3m * 0.5)
        y_pred = baseline * growth_ratio

        # La meta no debe exceder/caer irracionalmente respecto al promedio móvil actual.
        y_pred = max(mavg_3m * META_VS_PROMEDIO_MOVIL_MIN, min(y_pred, mavg_3m * META_VS_PROMEDIO_MOVIL_MAX))
        # Capping final contra el mismo mes del año anterior, para ciclos atípicos.
        y_pred = max(ventas_yoy * META_VS_ANIO_ANTERIOR_MIN, y_pred)

        meta_monto = max(ventas_ant, y_pred) * factor_presion
        return max(0.0, meta_monto)

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
