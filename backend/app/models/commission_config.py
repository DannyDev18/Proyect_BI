# backend/app/models/commission_config.py
"""Configuración del sistema de Comisiones Variables (docs/features/
plan_integracion_comisiones_variables.md, docs/auditoria/30_comisiones_variables.md).
Todas las tablas viven en `public.*` -- no se toca el esquema `edw` (regla de negocio
del proyecto: el DW es solo lectura/append desde el ETL)."""
import datetime

from sqlalchemy import (
    Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Index, Integer, Numeric, String,
    UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.database.session import Base


class ComisionMatrizCategoria(Base):
    """Matriz de tasas por categoría de producto (grupo A/B/C/S/X), indexada por el
    código `dim_producto.clase`/`subclase` -- NO por `nombre_clase` (auditoría 30, H2:
    100% vacío en el catálogo actual). Con vigencias: nunca se edita historia, se cierra
    la fila vieja (`vigente_hasta`) y se inserta una nueva."""
    __tablename__ = "comision_matriz_categorias"
    __table_args__ = (
        CheckConstraint("grupo IN ('A','B','C','S','X')", name="check_grupo_valido"),
        CheckConstraint("base IN ('margen','valor')", name="check_base_valida"),
        CheckConstraint("tasa_pct >= 0 AND tasa_pct <= 100", name="check_tasa_pct_valida"),
        CheckConstraint("factor_estrategico >= 0.5 AND factor_estrategico <= 1.5", name="check_factor_estrategico_valido"),
        {"schema": "public"},
    )

    id = Column(Integer, primary_key=True, index=True)
    clase = Column(String(5), nullable=False)  # '*' = default/comodín (grupo por defecto)
    subclase = Column(String(5), nullable=True)  # NULL = aplica a toda la clase
    grupo = Column(String(1), nullable=False)
    tasa_pct = Column(Numeric(6, 3), nullable=False)
    base = Column(String(10), nullable=False, default="margen")
    factor_estrategico = Column(Numeric(4, 2), nullable=False, default=1.0)
    vigente_desde = Column(Date, nullable=False)
    vigente_hasta = Column(Date, nullable=True)
    creado_por = Column(Integer, ForeignKey("public.usuarios.id", ondelete="SET NULL"), nullable=True)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ComisionFactorCredito(Base):
    """Factores de ajuste por plazo de crédito (§4 de la propuesta). Auditoría 30 (H4):
    el EDW actual solo tiene tráfico real en 0 y 30 días -- la tabla admite los 7 tramos
    completos de la propuesta como configuración latente, sin datos que la respalden
    todavía para los tramos > 30 días."""
    __tablename__ = "comision_factores_credito"
    __table_args__ = (
        CheckConstraint("factor >= 0 AND factor <= 1.5", name="check_factor_credito_valido"),
        CheckConstraint("dias_desde >= 0", name="check_dias_desde_valido"),
        {"schema": "public"},
    )

    id = Column(Integer, primary_key=True, index=True)
    dias_desde = Column(Integer, nullable=False)
    dias_hasta = Column(Integer, nullable=True)  # NULL = sin tope superior
    factor = Column(Numeric(4, 2), nullable=False)
    pct_al_facturar = Column(Numeric(5, 2), nullable=False, default=100.0)  # reservado fase 2 (split cobranza)
    vigente_desde = Column(Date, nullable=False)
    vigente_hasta = Column(Date, nullable=True)


class ComisionConfigVendedor(Base):
    """Tipo y parámetros de comisión por vendedor -- cubre la brecha B1 (auditoría 30):
    `edw.dim_vendedor` no tiene tipo externo/interno ni fecha de ingreso, así que se
    mantiene en `public.*` mediante gestión de gerencia, no en el EDW.

    Con vigencias (C-3, docs/features/plan_correcciones_pendientes.md; auditoría 35 H4):
    antes un cambio de tipo externo/interno se aplicaba retroactivamente a cualquier
    período cerrado que aún no se hubiera congelado por primera vez -- mismo patrón que
    `ComisionMatrizCategoria`/`ComisionFactorCredito`, nunca se edita una fila vigente,
    se cierra (`vigente_hasta`) y se inserta una nueva."""
    __tablename__ = "comision_config_vendedor"
    __table_args__ = (
        CheckConstraint("tipo IN ('externo','interno')", name="check_tipo_vendedor_valido"),
        CheckConstraint("factor_tipo >= 0 AND factor_tipo <= 1.5", name="check_factor_tipo_valido"),
        # A lo sumo una fila "abierta" (vigente_hasta NULL) por vendedor -- reemplaza el
        # UNIQUE plano que tenía id_vendedor_origen antes de admitir historial.
        Index(
            "uq_comision_config_vendedor_vigente", "id_vendedor_origen", unique=True,
            postgresql_where=text("vigente_hasta IS NULL"),
        ),
        {"schema": "public"},
    )

    id = Column(Integer, primary_key=True, index=True)
    id_vendedor_origen = Column(String(15), nullable=False)
    tipo = Column(String(10), nullable=False, default="externo")
    factor_tipo = Column(Numeric(4, 2), nullable=False, default=1.0)
    fecha_ingreso = Column(Date, nullable=True)
    activo = Column(Boolean, nullable=False, default=True)
    vigente_desde = Column(Date, nullable=False, default=lambda: datetime.date(1900, 1, 1))
    vigente_hasta = Column(Date, nullable=True)


class ComisionLiquidacion(Base):
    """Snapshot congelado de una liquidación mensual (piloto en sombra y cierre oficial).
    `detalle_json` guarda el desglose línea/categoría/crédito/bonos completo --
    salvaguarda 6 (transparencia total): el vendedor puede ver exactamente cómo se
    calculó cada peso, incluso de un período ya cerrado."""
    __tablename__ = "comision_liquidaciones"
    __table_args__ = (
        CheckConstraint("mes BETWEEN 1 AND 12", name="check_mes_liquidacion_valido"),
        CheckConstraint("esquema IN ('plana','variable')", name="check_esquema_valido"),
        CheckConstraint("modo IN ('sombra','oficial')", name="check_modo_liquidacion_valido"),
        UniqueConstraint("anio", "mes", "id_vendedor_origen", "esquema", "modo", name="uq_comision_liquidacion"),
        {"schema": "public"},
    )

    id = Column(Integer, primary_key=True, index=True)
    anio = Column(Integer, nullable=False)
    mes = Column(Integer, nullable=False)
    id_vendedor_origen = Column(String(15), nullable=False)
    esquema = Column(String(10), nullable=False)
    modo = Column(String(10), nullable=False)
    comision_total = Column(Numeric(15, 4), nullable=False)
    detalle_json = Column(JSONB, nullable=False)
    fecha_calculo = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ComisionConfigAuditoria(Base):
    """Bitácora append-only de cambios a la configuración de Comisiones Variables
    (matriz de categorías, factores de crédito, tipo de vendedor) -- cubre la Fase 2
    ítem 2 de docs/features/plan_actualizacion_modulo_metas_comisiones.md §3: hoy
    `comision_matriz_categorias` guarda `creado_por` en la fila vigente, pero un cambio
    posterior pierde ese rastro (se cierra la fila vieja, la nueva no dice qué cambió
    respecto a la anterior); `comision_factores_credito`/`comision_config_vendedor` ni
    eso. Nunca se actualiza ni se borra una fila -- es un log de auditoría, no estado."""
    __tablename__ = "comision_config_auditoria"
    __table_args__ = (
        CheckConstraint(
            "tabla IN ('comision_matriz_categorias', 'comision_factores_credito', 'comision_config_vendedor')",
            name="check_tabla_auditoria_valida",
        ),
        {"schema": "public"},
    )

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("public.usuarios.id", ondelete="SET NULL"), nullable=True)
    tabla = Column(String(50), nullable=False)
    accion = Column(String(20), nullable=False)
    detalle_json = Column(JSONB, nullable=False)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
