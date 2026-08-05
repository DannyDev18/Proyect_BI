# backend/app/models/replenishment_config.py
"""Configuración editable del motor de Reabastecimiento Inteligente (docs/features/
plan_reabastecimiento_inteligente.md §6.3, docs/auditoria/50_reabastecimiento_
inteligente.md). Mismo patrón sin vigencia histórica que `metas_config_modulos`/
`metas_config_parametros`: cada recomendación se recalcula al vuelo (no hay snapshot
congelado como en comisiones), así que un cambio de política solo afecta a la
próxima consulta -- no hace falta reconstruir "la config de hace 3 meses"."""
from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, Numeric, String, func, text
from sqlalchemy.orm import relationship

from app.database.session import Base

CLASES_ABC_VALIDAS = ("A", "B", "C")


class ReabastecimientoPolitica(Base):
    """Nivel de servicio objetivo por clase ABC (D-2 del plan) + parámetros globales del
    motor. Una fila por clase ABC -- catálogo cerrado de 3 filas, sembradas por la
    migración con los defaults recomendados por la auditoría 50 (A=97.5%, B=95%, C=90%)."""
    __tablename__ = "reabastecimiento_politica"
    __table_args__ = (
        CheckConstraint(f"clase_abc IN {CLASES_ABC_VALIDAS}", name="check_reabast_politica_clase_valida"),
        CheckConstraint("nivel_servicio > 0 AND nivel_servicio < 1", name="check_reabast_politica_nivel_servicio_rango"),
        {"schema": "public"},
    )

    id = Column(Integer, primary_key=True, index=True)
    clase_abc = Column(String(1), nullable=False, unique=True)
    nivel_servicio = Column(Numeric(4, 3), nullable=False)
    actualizado_por = Column(Integer, ForeignKey("public.usuarios.id", ondelete="SET NULL"), nullable=True)
    actualizado_en = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    usuario = relationship("User", foreign_keys=[actualizado_por], primaryjoin="User.id == ReabastecimientoPolitica.actualizado_por")


class ReabastecimientoLeadTime(Base):
    """Lead time configurable por especificidad (D-1 opción (a) del plan: el EDW no
    puede derivarlo hoy -- `Fact_Compras` solo tiene la fecha de factura, sin fecha de
    orden -- ver auditoría 50 A-0.1). Exactamente una de `producto`/`categoria`/
    `proveedor` identifica la fila (mutuamente excluyentes); `replenishment_engine.
    resolver_lead_time` resuelve por especificidad decreciente. Sin vigencia histórica
    (mismo criterio que la política): el motor lee siempre la configuración vigente."""
    __tablename__ = "reabastecimiento_lead_time"
    __table_args__ = (
        CheckConstraint(
            "(producto IS NOT NULL)::int + (categoria IS NOT NULL)::int + (proveedor IS NOT NULL)::int = 1",
            name="check_reabast_lead_time_un_solo_nivel",
        ),
        CheckConstraint("dias > 0", name="check_reabast_lead_time_dias_positivo"),
        # 3 índices únicos parciales (no un UniqueConstraint compuesto -- NULL nunca es
        # igual a NULL en Postgres, ver migración 0016 para el detalle): uno por nivel.
        Index("uq_reabast_lead_time_producto", "producto", unique=True, postgresql_where=text("producto IS NOT NULL")),
        Index("uq_reabast_lead_time_categoria", "categoria", unique=True, postgresql_where=text("categoria IS NOT NULL")),
        Index("uq_reabast_lead_time_proveedor", "proveedor", unique=True, postgresql_where=text("proveedor IS NOT NULL")),
        {"schema": "public"},
    )

    id = Column(Integer, primary_key=True, index=True)
    producto = Column(String(20), nullable=True)
    categoria = Column(String(5), nullable=True)
    proveedor = Column(String(200), nullable=True)
    dias = Column(Numeric(6, 1), nullable=False)
    actualizado_por = Column(Integer, ForeignKey("public.usuarios.id", ondelete="SET NULL"), nullable=True)
    actualizado_en = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    usuario = relationship("User", foreign_keys=[actualizado_por], primaryjoin="User.id == ReabastecimientoLeadTime.actualizado_por")
