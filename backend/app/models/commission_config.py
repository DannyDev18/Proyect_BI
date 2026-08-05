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
        CheckConstraint("factor >= 0 AND factor <= 2.0", name="check_factor_credito_valido"),
        CheckConstraint("dias_desde >= 0", name="check_dias_desde_valido"),
        {"schema": "public"},
    )

    id = Column(Integer, primary_key=True, index=True)
    dias_desde = Column(Integer, nullable=False)
    dias_hasta = Column(Integer, nullable=True)  # NULL = sin tope superior
    factor = Column(Numeric(4, 2), nullable=False)
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
    se cierra (`vigente_hasta`) y se inserta una nueva.

    Perfil `jefe_agencia` (auditoría 44, docs/features/plan_comisiones_sobre_cobros.md):
    tercer perfil real de la empresa, con tabla de tramos propia (RN-CM9) y un componente
    adicional de comisión (1% de ventas de contado de SU agencia, `agencia` = `establ`)."""
    __tablename__ = "comision_config_vendedor"
    __table_args__ = (
        CheckConstraint("tipo IN ('externo','interno','jefe_agencia')", name="check_tipo_vendedor_valido"),
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
    # Agencia (edw.dim_sucursal.establ) del jefe de agencia -- base del componente
    # 'contado_agencia' de la fórmula (§2.3 del plan). NULL para externo/interno.
    agencia = Column(String(3), nullable=True)
    vigente_desde = Column(Date, nullable=False, default=lambda: datetime.date(1900, 1, 1))
    vigente_hasta = Column(Date, nullable=True)


class ComisionTramoCobranza(Base):
    """Tramos de comisión sobre COBRANZA por perfil de vendedor (auditoría 44,
    docs/features/plan_comisiones_sobre_cobros.md §2.1) -- la regla realmente vigente en
    la empresa hoy: tasa según los días transcurridos entre la emisión de la factura y la
    fecha en que el cobro se hace efectivo (`edw.fact_cobros_cuotas.dias_cobro`, calculado
    sobre `banfec`, NUNCA sobre la fecha de recepción del cheque -- RN-CM8/RN-CM9).

    `dias_hasta` es el techo del tramo (21/60/90/120/365 del cuadro de negocio); NULL
    significa "sin tope superior" (equivalente al remanente > 365, tasa 0% en el cuadro
    original). Se resuelve por el primer tramo, en orden de `dias_hasta` ascendente, que
    cubre `dias_cobro` -- mismo patrón de resolución por especificidad que
    `ComisionMatrizCategoria`, pero por rango numérico en vez de por clase/subclase."""
    __tablename__ = "comision_tramos_cobranza"
    __table_args__ = (
        CheckConstraint("perfil IN ('externo','interno','jefe_agencia')", name="check_perfil_tramo_valido"),
        CheckConstraint("tasa_pct >= 0 AND tasa_pct <= 100", name="check_tasa_tramo_valida"),
        CheckConstraint("dias_hasta IS NULL OR dias_hasta >= 0", name="check_dias_hasta_valido"),
        {"schema": "public"},
    )

    id = Column(Integer, primary_key=True, index=True)
    perfil = Column(String(15), nullable=False)
    dias_hasta = Column(Integer, nullable=True)
    tasa_pct = Column(Numeric(6, 3), nullable=False)
    vigente_desde = Column(Date, nullable=False)
    vigente_hasta = Column(Date, nullable=True)
    creado_por = Column(Integer, ForeignKey("public.usuarios.id", ondelete="SET NULL"), nullable=True)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ComisionTramoCumplimiento(Base):
    """Tramos del multiplicador de `multiplicador_cumplimiento` (auditoría 45,
    docs/features/plan_comisiones_sobrecumplimiento_umbral_y_desglose.md) -- petición
    explícita del usuario: (1) sin comisión bajo el 90% de cumplimiento de meta (antes
    el tramo 80-89% pagaba 0.7x); (2) el sobrecumplimiento (>100%) deja de ser un
    escalón plano único (1.2x) y pasa a una escala configurable. Reemplaza los umbrales
    `UMBRAL_*`/multiplicadores `COMISION_MULT_*` de `commission_engine.py` como fuente
    de este componente del esquema VARIABLE -- el esquema plano legacy
    (`calcular_comision`) no se toca, sigue usando sus 4 tramos fijos.

    `perfil` NULL = aplica a todos (semilla actual); admite tramos distintos por
    externo/interno/jefe_agencia a futuro sin migración nueva, mismo patrón que
    `ComisionTramoCobranza`. `bono_fijo`: monto adicional en $ que se suma al
    componente `bonos` de la fórmula cuando el vendedor alcanza este tramo -- sembrado
    en 0.00, activarlo es decisión de gerencia."""
    __tablename__ = "comision_tramos_cumplimiento"
    __table_args__ = (
        CheckConstraint(
            "perfil IS NULL OR perfil IN ('externo','interno','jefe_agencia')",
            name="check_perfil_tramo_cumplimiento_valido",
        ),
        CheckConstraint("pct_desde >= 0", name="check_pct_desde_valido"),
        CheckConstraint("pct_hasta IS NULL OR pct_hasta > pct_desde", name="check_pct_hasta_valido"),
        CheckConstraint("multiplicador >= 0", name="check_multiplicador_cumplimiento_valido"),
        CheckConstraint("bono_fijo >= 0", name="check_bono_fijo_valido"),
        {"schema": "public"},
    )

    id = Column(Integer, primary_key=True, index=True)
    perfil = Column(String(15), nullable=True)
    pct_desde = Column(Numeric(6, 2), nullable=False)
    pct_hasta = Column(Numeric(6, 2), nullable=True)
    multiplicador = Column(Numeric(6, 4), nullable=False)
    etiqueta = Column(String(50), nullable=False)
    bono_fijo = Column(Numeric(12, 2), nullable=False, default=0)
    vigente_desde = Column(Date, nullable=False)
    vigente_hasta = Column(Date, nullable=True)
    creado_por = Column(Integer, ForeignKey("public.usuarios.id", ondelete="SET NULL"), nullable=True)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ComisionFormula(Base):
    """Estructura de la fórmula de comisión variable como configuración persistida, NO
    código (auditoría 44, pedido explícito del usuario: "la fórmula ... también puede ser
    editable y no quemada en código"). Una fórmula vigente es una tubería ORDENADA de
    componentes de un catálogo cerrado (`ComisionFormulaComponente.componente`, validado
    en el servicio, nunca evaluación de expresiones arbitrarias -- superficie de ejecución
    inaceptable en un módulo que mueve dinero real).

    A lo sumo una fórmula `activa` a la vez (índice parcial, mismo patrón que
    `ComisionConfigVendedor`)."""
    __tablename__ = "comision_formula"
    __table_args__ = (
        Index("uq_comision_formula_activa", "activa", unique=True, postgresql_where=text("activa = true")),
        {"schema": "public"},
    )

    id = Column(Integer, primary_key=True, index=True)
    clave = Column(String(30), nullable=False, unique=True)  # 'actual' | 'cobranza' | ...
    nombre = Column(String(100), nullable=False)
    activa = Column(Boolean, nullable=False, default=False)
    creado_por = Column(Integer, ForeignKey("public.usuarios.id", ondelete="SET NULL"), nullable=True)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ComisionFormulaComponente(Base):
    """Un paso de la tubería de una `ComisionFormula`. Catálogo cerrado de `componente`
    validado en `CommissionConfigService` (no en un CHECK de BD, para no requerir una
    migración cada vez que se habilite un componente ya soportado por el motor pero
    todavía no expuesto en ninguna fórmula)."""
    __tablename__ = "comision_formula_componente"
    __table_args__ = (
        CheckConstraint("operador IN ('sumar','restar','multiplicar')", name="check_operador_formula_valido"),
        UniqueConstraint("formula_id", "orden", name="uq_formula_orden"),
        {"schema": "public"},
    )

    id = Column(Integer, primary_key=True, index=True)
    formula_id = Column(Integer, ForeignKey("public.comision_formula.id", ondelete="CASCADE"), nullable=False)
    orden = Column(Integer, nullable=False)
    componente = Column(String(30), nullable=False)
    operador = Column(String(12), nullable=False)
    activo = Column(Boolean, nullable=False, default=True)
    parametros = Column(JSONB, nullable=False, default=dict)


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
            "tabla IN ('comision_matriz_categorias', 'comision_factores_credito', 'comision_config_vendedor', "
            "'comision_tramos_cobranza', 'comision_formula', 'comision_tramos_cumplimiento')",
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
