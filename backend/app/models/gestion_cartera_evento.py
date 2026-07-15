# backend/app/models/gestion_cartera_evento.py
from sqlalchemy import Column, BigInteger, Integer, String, ForeignKey, DateTime, Text, func, CheckConstraint
from app.database.session import Base


class GestionCarteraEvento(Base):
    """
    Registro de gestión del módulo Ventas — Cartera de Clientes 360.
    Mapeada a: public.gestion_cartera_eventos
    Ver docs/features/propuesta_nuevos_modulos_roi.md §4, auditoría 32.
    Mismo espíritu que la telemetría de Venta Cruzada (public.recomendaciones_eventos,
    RN-CS2): el vendedor marca el resultado de cada contacto, creando el dato de
    efectividad que hoy no existe.
    """
    __tablename__ = "gestion_cartera_eventos"
    __table_args__ = (
        CheckConstraint("evento IN ('contactado', 'recompro', 'perdido')", name="check_gestion_evento_valido"),
        {"schema": "public"},
    )

    id = Column(BigInteger, primary_key=True, index=True)
    fecha = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    usuario_id = Column(Integer, ForeignKey("public.usuarios.id", ondelete="SET NULL"), nullable=True)
    cliente_sk = Column(Integer, nullable=True)
    evento = Column(String(20), nullable=False)
    motivo = Column(Text, nullable=True)
