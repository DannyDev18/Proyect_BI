# backend/app/models/replenishment_proposal.py
"""Gestión operativa del Reabastecimiento Inteligente (docs/features/plan_
reabastecimiento_inteligente.md §6.3/§8 F9): propuestas de compra persistidas -- a
diferencia de `reabastecimiento_politica`/`_lead_time` (config viva, sin vigencia),
una propuesta ya creada guarda un SNAPSHOT congelado de la justificación de cada
línea (mismo criterio que `comision_liquidaciones`: no se recalcula al mirarla, para
que aprobar/rechazar sea sobre lo que el usuario realmente vio, no sobre un número que
cambió mientras decidía)."""
from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database.session import Base

ESTADOS_PROPUESTA_COMPRA = ("borrador", "aprobada", "rechazada", "exportada")


class PropuestaCompra(Base):
    """Cabecera. `filtros_origen` guarda los filtros (almacén/categoría/proveedor/
    horizonte) con los que se generó, para que quien la revise sepa el alcance sin
    adivinar."""
    __tablename__ = "propuesta_compra"
    __table_args__ = (
        CheckConstraint(f"estado IN {ESTADOS_PROPUESTA_COMPRA}", name="check_propuesta_compra_estado_valido"),
        {"schema": "public"},
    )

    id = Column(Integer, primary_key=True, index=True)
    estado = Column(String(20), nullable=False, default="borrador")
    usuario_id = Column(Integer, ForeignKey("public.usuarios.id", ondelete="SET NULL"), nullable=True)
    filtros_origen = Column(JSONB, nullable=False, default=dict)
    horizonte_dias = Column(Numeric(6, 1), nullable=False)
    total = Column(Numeric(14, 2), nullable=False, default=0)
    creado_en = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    actualizado_en = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    usuario = relationship("User", foreign_keys=[usuario_id], primaryjoin="User.id == PropuestaCompra.usuario_id")
    lineas = relationship(
        "PropuestaCompraLinea", back_populates="propuesta", cascade="all, delete-orphan", order_by="PropuestaCompraLinea.id",
    )


class PropuestaCompraLinea(Base):
    __tablename__ = "propuesta_compra_linea"
    __table_args__ = ({"schema": "public"},)

    id = Column(Integer, primary_key=True, index=True)
    propuesta_id = Column(Integer, ForeignKey("public.propuesta_compra.id", ondelete="CASCADE"), nullable=False, index=True)
    codart = Column(String(50), nullable=False)
    nombre = Column(String(200), nullable=False)
    cantidad = Column(Numeric(12, 2), nullable=False)
    costo_unitario = Column(Numeric(12, 4), nullable=False)
    costo_total = Column(Numeric(14, 2), nullable=False)
    justificacion = Column(JSONB, nullable=False, default=dict)

    propuesta = relationship("PropuestaCompra", back_populates="lineas")
