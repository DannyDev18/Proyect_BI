"""comisiones sobre cobros

Revision ID: 0008_comisiones_cobranza
Revises: 0007_tokens_revocados
Create Date: 2026-07-30 00:00:00.000000

Auditoría 44 (docs/auditoria/44_comisiones_sobre_cobros.md) + plan de ejecución
(docs/features/plan_comisiones_sobre_cobros.md): incorpora al esquema de Comisiones
Variables la regla realmente vigente en la empresa -- comisión sobre COBRANZA efectiva
por tramo de días de cobro, más el componente "1% de ventas de contado" de los jefes de
agencia -- como configuración adicional, sin tocar el motor plano ni romper el esquema
de margen/categoría existente.

Tres piezas:
  1. `comision_tramos_cobranza`: tramos/tasas por perfil (externo/interno/jefe_agencia),
     con vigencia -- mismo patrón que `comision_matriz_categorias`.
  2. `comision_formula` + `comision_formula_componente`: la ESTRUCTURA de la fórmula deja
     de estar quemada en código (pedido explícito del usuario) -- una tubería ordenada de
     componentes de un catálogo cerrado. Se siembran dos fórmulas: 'actual' (activa,
     reproduce el motor existente -- líneas de venta × tipo × cumplimiento − devoluciones
     + bonos) y 'cobranza' (inactiva, cobranza + contado de agencia), para que esta
     migración sea un no-op de comportamiento hasta que gerencia active la segunda.
  3. `comision_config_vendedor` gana el perfil `jefe_agencia` (antes solo
     externo/interno) y la columna `agencia` (establ) que ese perfil necesita para el
     componente de ventas de contado.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0008_comisiones_cobranza'
down_revision: Union[str, None] = '0007_tokens_revocados'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. comision_config_vendedor: perfil jefe_agencia + columna agencia ──────────
    op.drop_constraint('check_tipo_vendedor_valido', 'comision_config_vendedor', schema='public', type_='check')
    op.create_check_constraint(
        'check_tipo_vendedor_valido', 'comision_config_vendedor',
        "tipo IN ('externo','interno','jefe_agencia')", schema='public',
    )
    op.add_column(
        'comision_config_vendedor', sa.Column('agencia', sa.String(length=3), nullable=True), schema='public',
    )

    # ── 2. comision_tramos_cobranza ──────────────────────────────────────────────────
    op.create_table(
        'comision_tramos_cobranza',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('perfil', sa.String(length=15), nullable=False),
        sa.Column('dias_hasta', sa.Integer(), nullable=True),
        sa.Column('tasa_pct', sa.Numeric(6, 3), nullable=False),
        sa.Column('vigente_desde', sa.Date(), nullable=False),
        sa.Column('vigente_hasta', sa.Date(), nullable=True),
        sa.Column('creado_por', sa.Integer(), nullable=True),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("perfil IN ('externo','interno','jefe_agencia')", name='check_perfil_tramo_valido'),
        sa.CheckConstraint("tasa_pct >= 0 AND tasa_pct <= 100", name='check_tasa_tramo_valida'),
        sa.CheckConstraint("dias_hasta IS NULL OR dias_hasta >= 0", name='check_dias_hasta_valido'),
        sa.ForeignKeyConstraint(['creado_por'], ['public.usuarios.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        schema='public',
    )
    op.create_index(
        op.f('ix_public_comision_tramos_cobranza_id'), 'comision_tramos_cobranza', ['id'],
        unique=False, schema='public',
    )

    # ── 3. comision_formula / comision_formula_componente ───────────────────────────
    op.create_table(
        'comision_formula',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('clave', sa.String(length=30), nullable=False),
        sa.Column('nombre', sa.String(length=100), nullable=False),
        sa.Column('activa', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('creado_por', sa.Integer(), nullable=True),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['creado_por'], ['public.usuarios.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('clave', name='uq_comision_formula_clave'),
        schema='public',
    )
    op.create_index(
        op.f('ix_public_comision_formula_id'), 'comision_formula', ['id'], unique=False, schema='public',
    )
    op.create_index(
        'uq_comision_formula_activa', 'comision_formula', ['activa'], unique=True,
        postgresql_where=sa.text('activa = true'), schema='public',
    )

    op.create_table(
        'comision_formula_componente',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('formula_id', sa.Integer(), nullable=False),
        sa.Column('orden', sa.Integer(), nullable=False),
        sa.Column('componente', sa.String(length=30), nullable=False),
        sa.Column('operador', sa.String(length=12), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('parametros', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint("operador IN ('sumar','restar','multiplicar')", name='check_operador_formula_valido'),
        sa.ForeignKeyConstraint(['formula_id'], ['public.comision_formula.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('formula_id', 'orden', name='uq_formula_orden'),
        schema='public',
    )
    op.create_index(
        op.f('ix_public_comision_formula_componente_id'), 'comision_formula_componente', ['id'],
        unique=False, schema='public',
    )

    # ── 4. comision_config_auditoria: bitácora cubre las 2 tablas nuevas ────────────
    op.drop_constraint('check_tabla_auditoria_valida', 'comision_config_auditoria', schema='public', type_='check')
    op.create_check_constraint(
        'check_tabla_auditoria_valida', 'comision_config_auditoria',
        "tabla IN ('comision_matriz_categorias', 'comision_factores_credito', 'comision_config_vendedor', "
        "'comision_tramos_cobranza', 'comision_formula')",
        schema='public',
    )

    # ── 5. Semilla: tramos exactos del cuadro de negocio (auditoría 44 §1) ──────────
    # 'interno' se siembra igual que 'externo' -- el documento de negocio no declara una
    # tabla propia para interno; gerencia la ajusta desde el panel si corresponde.
    tramos_tbl = sa.table(
        'comision_tramos_cobranza',
        sa.column('perfil', sa.String), sa.column('dias_hasta', sa.Integer),
        sa.column('tasa_pct', sa.Numeric), sa.column('vigente_desde', sa.Date),
    )
    hoy = '1900-01-01'
    op.bulk_insert(tramos_tbl, [
        {'perfil': 'externo', 'dias_hasta': 21, 'tasa_pct': 2.00, 'vigente_desde': hoy},
        {'perfil': 'externo', 'dias_hasta': 60, 'tasa_pct': 1.75, 'vigente_desde': hoy},
        {'perfil': 'externo', 'dias_hasta': 90, 'tasa_pct': 0.75, 'vigente_desde': hoy},
        {'perfil': 'externo', 'dias_hasta': 120, 'tasa_pct': 0.50, 'vigente_desde': hoy},
        {'perfil': 'externo', 'dias_hasta': 365, 'tasa_pct': 0.00, 'vigente_desde': hoy},
        {'perfil': 'interno', 'dias_hasta': 21, 'tasa_pct': 2.00, 'vigente_desde': hoy},
        {'perfil': 'interno', 'dias_hasta': 60, 'tasa_pct': 1.75, 'vigente_desde': hoy},
        {'perfil': 'interno', 'dias_hasta': 90, 'tasa_pct': 0.75, 'vigente_desde': hoy},
        {'perfil': 'interno', 'dias_hasta': 120, 'tasa_pct': 0.50, 'vigente_desde': hoy},
        {'perfil': 'interno', 'dias_hasta': 365, 'tasa_pct': 0.00, 'vigente_desde': hoy},
        {'perfil': 'jefe_agencia', 'dias_hasta': 21, 'tasa_pct': 1.00, 'vigente_desde': hoy},
        {'perfil': 'jefe_agencia', 'dias_hasta': 60, 'tasa_pct': 1.75, 'vigente_desde': hoy},
        {'perfil': 'jefe_agencia', 'dias_hasta': 90, 'tasa_pct': 0.75, 'vigente_desde': hoy},
        {'perfil': 'jefe_agencia', 'dias_hasta': 120, 'tasa_pct': 0.50, 'vigente_desde': hoy},
        {'perfil': 'jefe_agencia', 'dias_hasta': 365, 'tasa_pct': 0.00, 'vigente_desde': hoy},
    ])

    # ── 6. Semilla: 2 fórmulas (auditoría 44 §2.2) ──────────────────────────────────
    formula_tbl = sa.table(
        'comision_formula',
        sa.column('id', sa.Integer), sa.column('clave', sa.String),
        sa.column('nombre', sa.String), sa.column('activa', sa.Boolean),
    )
    conn = op.get_bind()
    id_actual = conn.execute(
        formula_tbl.insert().returning(formula_tbl.c.id),
        {'clave': 'actual', 'nombre': 'Margen/categoría (esquema vigente)', 'activa': True},
    ).scalar()
    id_cobranza = conn.execute(
        formula_tbl.insert().returning(formula_tbl.c.id),
        {'clave': 'cobranza', 'nombre': 'Comisión sobre cobros + contado de agencia', 'activa': False},
    ).scalar()

    componente_tbl = sa.table(
        'comision_formula_componente',
        sa.column('formula_id', sa.Integer), sa.column('orden', sa.Integer),
        sa.column('componente', sa.String), sa.column('operador', sa.String),
    )
    # 'actual' reproduce byte a byte la fórmula hoy quemada en
    # commission_engine.calcular_comision_variable -- esta migración es un no-op de
    # comportamiento hasta que gerencia active 'cobranza'.
    op.bulk_insert(componente_tbl, [
        {'formula_id': id_actual, 'orden': 1, 'componente': 'base_lineas_venta', 'operador': 'sumar'},
        {'formula_id': id_actual, 'orden': 2, 'componente': 'factor_tipo_vendedor', 'operador': 'multiplicar'},
        {'formula_id': id_actual, 'orden': 3, 'componente': 'multiplicador_cumplimiento', 'operador': 'multiplicar'},
        {'formula_id': id_actual, 'orden': 4, 'componente': 'devoluciones', 'operador': 'restar'},
        {'formula_id': id_actual, 'orden': 5, 'componente': 'bonos', 'operador': 'sumar'},
        {'formula_id': id_cobranza, 'orden': 1, 'componente': 'base_cobranza', 'operador': 'sumar'},
        {'formula_id': id_cobranza, 'orden': 2, 'componente': 'contado_agencia', 'operador': 'sumar'},
        {'formula_id': id_cobranza, 'orden': 3, 'componente': 'devoluciones', 'operador': 'restar'},
        {'formula_id': id_cobranza, 'orden': 4, 'componente': 'bonos', 'operador': 'sumar'},
    ])


def downgrade() -> None:
    op.drop_table('comision_formula_componente', schema='public')
    op.drop_index('uq_comision_formula_activa', table_name='comision_formula', schema='public')
    op.drop_index(op.f('ix_public_comision_formula_id'), table_name='comision_formula', schema='public')
    op.drop_table('comision_formula', schema='public')
    op.drop_index(
        op.f('ix_public_comision_tramos_cobranza_id'), table_name='comision_tramos_cobranza', schema='public',
    )
    op.drop_table('comision_tramos_cobranza', schema='public')

    op.drop_constraint('check_tabla_auditoria_valida', 'comision_config_auditoria', schema='public', type_='check')
    op.create_check_constraint(
        'check_tabla_auditoria_valida', 'comision_config_auditoria',
        "tabla IN ('comision_matriz_categorias', 'comision_factores_credito', 'comision_config_vendedor')",
        schema='public',
    )

    op.drop_column('comision_config_vendedor', 'agencia', schema='public')
    op.drop_constraint('check_tipo_vendedor_valido', 'comision_config_vendedor', schema='public', type_='check')
    op.create_check_constraint(
        'check_tipo_vendedor_valido', 'comision_config_vendedor', "tipo IN ('externo','interno')", schema='public',
    )
