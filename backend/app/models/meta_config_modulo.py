# backend/app/models/meta_config_modulo.py
"""Configuración modular del motor de metas v3 (docs/features/plan_motor_metas_v3_y_
comisiones_unificadas.md §9/§18, Fase 6): una fila por etapa del pipeline de 14 etapas
(catálogo cerrado en `app/services/goal_pipeline_stages.py::ETAPAS_CATALOGO`), con su
método, si está activa, su orden (fijo, informativo -- el orden de EJECUCIÓN real es
código, no dato, ver §18.bis del plan) y sus parámetros en JSONB.

Reemplaza a `metas_config_parametros` (13 constantes planas, motor v2, migración
`0013_motor_metas_v2`) como la fuente de verdad editable -- esa tabla se CONSERVA (no se
elimina, mismo criterio que `comision_factores_credito` tras su retiro funcional) por si
alguna herramienta de diagnóstico externa aún la referencia, pero el motor real ya no la
lee. Mismo patrón sin vigencia histórica que `metas_config_parametros`: cada meta ya
persiste su propia `trazabilidad_calculo` completa, así que un cambio de configuración
solo afecta a las metas que se generen A PARTIR de ahora."""
from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database.session import Base

# E12_distribucion/E14_potencial retirados (migración 0015_metas_pipeline_ajustes):
# nunca tuvieron un método implementado -- ver docstring del módulo.
ETAPAS_VALIDAS_SQL = (
    "'E1_limpieza','E2_nivel_base','E3_estacionalidad','E4_tendencia','E5_estabilidad',"
    "'E6_madurez','E7_estrategia','E8_tipo_vendedor','E9_capacidad','E10_restricciones',"
    "'E11_redondeo','E13_cartera','E15_cumplimiento','E16_volatilidad'"
)


class MetaConfigModulo(Base):
    __tablename__ = "metas_config_modulos"
    __table_args__ = (
        CheckConstraint(f"etapa IN ({ETAPAS_VALIDAS_SQL})", name="check_meta_config_modulo_etapa_valida"),
        {"schema": "public"},
    )

    id = Column(Integer, primary_key=True, index=True)
    etapa = Column(String(40), nullable=False, unique=True)
    metodo = Column(String(40), nullable=True)
    activo = Column(Boolean, nullable=False, default=False)
    orden = Column(Integer, nullable=False)
    parametros = Column(JSONB, nullable=False, server_default="{}")
    razon_desactivacion = Column(String(300), nullable=True)
    actualizado_por = Column(Integer, ForeignKey("public.usuarios.id", ondelete="SET NULL"), nullable=True)
    actualizado_en = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    usuario = relationship("User", foreign_keys=[actualizado_por], primaryjoin="User.id == MetaConfigModulo.actualizado_por")
