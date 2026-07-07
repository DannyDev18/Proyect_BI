# backend/app/models/goal.py
from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, DateTime, func, CheckConstraint
from sqlalchemy.orm import relationship
from app.db.session import Base

class Goal(Base):
    """
    Tabla de metas comerciales operativas
    Mapeada a: public.metas_comerciales_operativas
    """
    __tablename__ = "metas_comerciales_operativas"
    __table_args__ = (
        CheckConstraint('anio >= 2020', name='check_anio_valido'),
        CheckConstraint('mes BETWEEN 1 AND 12', name='check_mes_valido'),
        CheckConstraint('monto_meta >= 0', name='check_monto_meta_valido'),
        CheckConstraint('unidades_meta >= 0', name='check_unidades_meta_valido'),
        CheckConstraint('comision_base_pct BETWEEN 0 AND 100', name='check_comision_base_pct_valida'),
        CheckConstraint('bono_sobrecumplimiento >= 0', name='check_bono_sobre_valido'),
        CheckConstraint(
            "estado IN ('PROPUESTA', 'APROBADA', 'RECHAZADA')",
            name='check_estado_valido'
        ),
        {"schema": "public"}
    )

    # Nota: SQLAlchemy Sync para BIGINT GENERATED ALWAYS AS IDENTITY se puede declarar como BigInteger e identity=True
    # o usar Integer con autoincrement. Para simplicidad con Postgres lo usaremos así:
    id = Column(Integer, primary_key=True, index=True)
    anio = Column(Integer, nullable=False)
    mes = Column(Integer, nullable=False)

    id_vendedor_origen = Column(String(15), nullable=True)
    sucursal = Column(String(100), nullable=False)

    monto_meta = Column(Numeric(15, 4), nullable=False, default=0.0000)
    unidades_meta = Column(Numeric(15, 4), nullable=False, default=0.0000)
    comision_base_pct = Column(Numeric(5, 2), nullable=False, default=2.00)
    bono_sobrecumplimiento = Column(Numeric(15, 4), nullable=False, default=100.0000)

    estado = Column(String(20), nullable=False, default="PROPUESTA")
    approved_by = Column(Integer, ForeignKey("public.usuarios.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relaciones
    # usuario: el vendedor asignado
    vendedor = relationship("User", foreign_keys=[id_vendedor_origen], primaryjoin="User.id_vendedor_origen == Goal.id_vendedor_origen")
    # aprobador
    aprobador = relationship("User", foreign_keys=[approved_by], primaryjoin="User.id == Goal.approved_by")

