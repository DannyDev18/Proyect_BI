# backend/app/models/anomalia_revision.py
"""Triage de anomalías transaccionales (Fase 2 Admin, docs/features/
plan_correcciones_pendientes.md §3; auditoría 36 confirmó que /admin/anomalies es una
consulta puntual por transacción, no un listado -- esta tabla es lo que convierte cada
detección en un ítem de trabajo con estado, en vez de un resultado que se pierde al
cerrar la pantalla."""
from sqlalchemy import (
    CheckConstraint, Column, DateTime, ForeignKey, Integer, Numeric, String, Text, func,
)
from app.database.session import Base


class AnomaliaRevision(Base):
    """
    Una fila por transacción calificada como anómala por el modelo Isolation Forest.
    Se crea (si no existe ya) cuando GET /admin/anomalies detecta es_anomalia=True.
    Mapeada a: public.anomalias_revisiones
    """
    __tablename__ = "anomalias_revisiones"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('nueva', 'revisada', 'descartada', 'confirmada')",
            name="check_estado_revision_valido",
        ),
        {"schema": "public"},
    )

    id              = Column(Integer, primary_key=True, index=True)
    transaccion_id  = Column(String(50), nullable=False, unique=True, index=True)
    score           = Column(Numeric(10, 4), nullable=False)
    estado          = Column(String(20), nullable=False, default="nueva", index=True)
    revisor_id      = Column(Integer, ForeignKey("public.usuarios.id", ondelete="SET NULL"), nullable=True)
    nota            = Column(Text, nullable=True)
    fecha_deteccion = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    fecha_revision  = Column(DateTime(timezone=True), nullable=True)
