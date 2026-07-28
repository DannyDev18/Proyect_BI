# backend/app/repositories/ml_model_run_repository.py
"""Lectura de `public.ml_model_runs` (Fase 3, docs/features/plan_mejora_pipeline_ml.md
§5.1) -- las filas las escribe el proceso `ml` (contenedor separado, misma base de
datos), este repositorio solo lee para el panel MLOps del administrador."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.ml_model_run import MLModelRun


class MLModelRunRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_recientes(self, clave: str | None = None, limit: int = 500) -> list[MLModelRun]:
        query = self.db.query(MLModelRun)
        if clave:
            query = query.filter(MLModelRun.clave == clave)
        return query.order_by(MLModelRun.creado_en.desc()).limit(limit).all()
