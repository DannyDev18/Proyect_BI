# backend/app/models/meta_config.py
"""Configuración editable del motor de metas v2 (docs/features/plan_motor_metas_
configurable.md §5.5, docs/auditoria/46_motor_metas_configurable.md). Mismo patrón que
`comision_config_vendedor`/`comision_tramos_cumplimiento`: el gerente edita PARÁMETROS de
una fórmula fija y auditada, nunca una expresión libre -- sin superficie de evaluación
arbitraria sobre un cálculo que mueve dinero real (la meta es el denominador del % de
cumplimiento que fija el multiplicador de comisión, auditoría 45).

A diferencia de `comision_tramos_cumplimiento` (con vigencia por fecha, porque una
liquidación de comisión ya pagada puede necesitar reconstruirse con la configuración
vigente EN ESE MOMENTO), `metas_config_parametros` es una fila viva por clave, sin
vigencia histórica: una meta ya generada guarda su propia trazabilidad completa
(`Goal.trazabilidad_calculo`), así que nunca necesita re-resolver "la configuración de
hace 3 meses" -- cambiar un parámetro solo afecta a las metas que se generen A PARTIR de
ahora. El historial de cambios vive en `comision_config_auditoria` (bitácora genérica ya
existente, reutilizada aquí)."""
from sqlalchemy import Column, Integer, Numeric, String, ForeignKey, DateTime, func, CheckConstraint
from sqlalchemy.orm import relationship
from app.database.session import Base


class MetaConfigParametro(Base):
    __tablename__ = "metas_config_parametros"
    __table_args__ = (
        CheckConstraint('valor > 0', name='check_meta_config_valor_positivo'),
        {"schema": "public"}
    )

    id = Column(Integer, primary_key=True, index=True)
    clave = Column(String(60), nullable=False, unique=True)
    valor = Column(Numeric(10, 4), nullable=False)
    descripcion = Column(String(300), nullable=True)
    actualizado_por = Column(Integer, ForeignKey("public.usuarios.id", ondelete="SET NULL"), nullable=True)
    actualizado_en = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    usuario = relationship("User", foreign_keys=[actualizado_por], primaryjoin="User.id == MetaConfigParametro.actualizado_por")
