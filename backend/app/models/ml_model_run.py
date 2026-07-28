# backend/app/models/ml_model_run.py
"""Bitácora append-only de corridas de reentrenamiento con gating (Fase 3,
docs/features/plan_mejora_pipeline_ml.md §5.1). Cada fila la escribe
`ml/src/training/promotion.py` (proceso `ml`, misma base de datos Postgres, esquema
`public`) tras evaluar un candidato contra el campeón vigente de `ml/models/registry.json`
-- promovido o rechazado, con ambas métricas. Nunca se actualiza ni se borra una fila
(mismo patrón que `ComisionConfigAuditoria`): es un log de auditoría de MLOps, no estado."""
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB

from app.database.session import Base


class MLModelRun(Base):
    __tablename__ = "ml_model_runs"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True, index=True)
    clave = Column(String(30), nullable=False, index=True)
    version_candidato = Column(String(20), nullable=False)
    version_campeon_anterior = Column(String(20), nullable=True)
    promovido = Column(Boolean, nullable=False)
    metrica_nombre = Column(String(50), nullable=True)
    metrica_candidato = Column(Float, nullable=True)
    metrica_campeon_anterior = Column(Float, nullable=True)
    razon = Column(Text, nullable=False)
    metrics_candidato = Column(JSONB, nullable=False)
    metrics_campeon_anterior = Column(JSONB, nullable=True)
    disparado_por = Column(String(20), nullable=False, server_default="manual")
    creado_en = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
