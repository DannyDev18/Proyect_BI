# backend/app/models/recommendation_event.py
from sqlalchemy import Column, BigInteger, Integer, String, Numeric, ForeignKey, DateTime, Text, func, CheckConstraint
from app.database.session import Base


class RecommendationEvent(Base):
    """
    Telemetría del módulo de Venta Cruzada (Cross-Selling).
    Mapeada a: public.recomendaciones_eventos
    Ver docs/auditoria/25_modulo_cross_selling.md y regla RN-CS2.
    """
    __tablename__ = "recomendaciones_eventos"
    __table_args__ = (
        CheckConstraint("evento IN ('mostrada', 'aceptada', 'rechazada')", name="check_evento_valido"),
        {"schema": "public"},
    )

    id = Column(BigInteger, primary_key=True, index=True)
    fecha = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    usuario_id = Column(Integer, ForeignKey("public.usuarios.id", ondelete="SET NULL"), nullable=True)
    cliente_sk = Column(Integer, nullable=True)
    producto_origen_cod = Column(String(20), nullable=False)
    producto_sugerido_cod = Column(String(20), nullable=False)
    score_lift = Column(Numeric(12, 6), nullable=True)
    motivo = Column(Text, nullable=True)
    evento = Column(String(20), nullable=False)
    fecha_carga = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
