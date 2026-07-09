# backend/tests/integration/test_goals_generation.py
"""Migrado de `backend/test_analytics.py` (script manual que creaba su propio engine
con credenciales hardcodeadas y llamaba `GoalsAutomationService.generar_propuestas_metas`
directamente, sin asserts). Ahora prueba `GoalsService.generate_proposals` a través de
la capa de dependencias real (`GoalRepository` + `ModelLoader`), con fixtures en vez de
credenciales embebidas.

Nota: esta prueba ESCRIBE en `public.metas_comerciales_operativas` del EDW de prueba
(mismo comportamiento del script original) -- por eso vive en integration, no en unit."""
import datetime

import pytest

from app.database.session import SessionLocal
from app.ml.model_loader import ModelLoader
from app.repositories.goal_repository import GoalRepository
from app.services.goals_service import GoalsService

pytestmark = pytest.mark.integration


def test_generate_proposals_no_lanza_excepcion_y_retorna_entero():
    db = SessionLocal()
    try:
        loader = ModelLoader(models_dir="c:/Proyect_BI/ml/models")
        loader.load_all()
        service = GoalsService(GoalRepository(db), loader)

        # Período de prueba: mes actual del EDW (siempre tiene historial reciente).
        now = datetime.datetime.now()
        registros = service.generate_proposals(anio=now.year, mes=now.month, factor_presion=1.10)

        assert isinstance(registros, int)
        assert registros >= 0
    finally:
        db.close()
