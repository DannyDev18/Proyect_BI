# backend/app/models/notification.py
from sqlalchemy import Column, BigInteger, Integer, String, Text, DateTime, ForeignKey, func, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
from app.database.session import Base


class Notification(Base):
    """
    Notificaciones persistidas del módulo de Notificaciones Inteligentes
    (docs/features/plan_modulo_notificaciones.md, docs/auditoria/31_modulo_notificaciones.md,
    reglas RN-N1..RN-N4). Solo eventos puntuales que requieren estado de lectura
    (anomalía detectada, meta generada, liquidación disponible); las notificaciones
    calculadas al vuelo (stock, forecast, churn) NO se persisten aquí.
    Mapeada a: public.notificaciones
    """
    __tablename__ = "notificaciones"
    __table_args__ = (
        CheckConstraint("prioridad IN ('alta', 'media', 'baja')", name="check_prioridad_valida"),
        {"schema": "public"},
    )

    id             = Column(BigInteger, primary_key=True, index=True)
    tipo_evento    = Column(String(50), nullable=False, index=True)
    rol_destino    = Column(String(20), ForeignKey("public.roles.nombre", ondelete="CASCADE"), nullable=False, index=True)
    usuario_id     = Column(Integer, ForeignKey("public.usuarios.id", ondelete="CASCADE"), nullable=True)
    titulo         = Column(String(200), nullable=False)
    mensaje        = Column(Text, nullable=False)
    accion_url     = Column(String(300), nullable=True)
    prioridad      = Column(String(10), nullable=False, default="media")
    contexto       = Column(JSONB, nullable=True)
    leida_por      = Column(JSONB, nullable=False, default=list)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    fecha_expira   = Column(DateTime(timezone=True), nullable=True)
