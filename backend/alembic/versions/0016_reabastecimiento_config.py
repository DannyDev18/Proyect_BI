"""reabastecimiento: politica de nivel de servicio por ABC + lead time configurable

Revision ID: 0016_reabastecimiento
Revises: 0015_metas_pipeline_ajustes
Create Date: 2026-08-04 12:00:00.000000

Fase 2 de docs/features/plan_reabastecimiento_inteligente.md (auditoría docs/auditoria/
50_reabastecimiento_inteligente.md). Dos tablas, sin vigencia histórica (mismo criterio
que `metas_config_modulos`: el motor recalcula al vuelo, un cambio de política solo
afecta a la próxima consulta):

- `reabastecimiento_politica`: nivel de servicio objetivo por clase ABC (D-2 del plan).
  Sembrada con los defaults recomendados (A=97.5%, B=95%, C=90%) -- catálogo cerrado de
  3 filas.
- `reabastecimiento_lead_time`: resuelve D-1 (el EDW no puede derivar el lead time real
  hoy -- `Fact_Compras` solo tiene fecha de factura, sin fecha de orden, confirmado en
  la auditoría 50 A-0.1) como tabla de configuración editable por producto/categoría/
  proveedor -- SIN fila de default global (el default sigue viviendo en
  `settings.BODEGA_LEAD_TIME_DIAS`, ya en 7 días, para no cambiar el comportamiento
  observado el día que se activa el motor nuevo -- el cambio de fórmula ya es
  suficiente impacto, ver A-0.7); `replenishment_engine.resolver_lead_time` recibe ese
  default como parámetro explícito, nunca lo busca en esta tabla.

Sin `propuesta_compra`/`propuesta_compra_linea`/`transferencia_decision` (Fase 9 del
plan, gestión operativa): fuera del corte mínimo de valor F0-F4, se crean en su propia
migración cuando esa fase se aborde.

Nombre de revisión <= 32 caracteres (lección de las migraciones 0012/0014/0015):
'0016_reabastecimiento' tiene 22.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0016_reabastecimiento'
down_revision: Union[str, None] = '0015_metas_pipeline_ajustes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'reabastecimiento_politica',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('clase_abc', sa.String(length=1), nullable=False),
        sa.Column('nivel_servicio', sa.Numeric(4, 3), nullable=False),
        sa.Column('actualizado_por', sa.Integer(), nullable=True),
        sa.Column('actualizado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("clase_abc IN ('A', 'B', 'C')", name='check_reabast_politica_clase_valida'),
        sa.CheckConstraint('nivel_servicio > 0 AND nivel_servicio < 1', name='check_reabast_politica_nivel_servicio_rango'),
        sa.ForeignKeyConstraint(['actualizado_por'], ['public.usuarios.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('clase_abc', name='uq_reabast_politica_clase'),
        schema='public',
    )
    op.create_index(op.f('ix_public_reabastecimiento_politica_id'), 'reabastecimiento_politica', ['id'], unique=False, schema='public')

    op.create_table(
        'reabastecimiento_lead_time',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('producto', sa.String(length=20), nullable=True),
        sa.Column('categoria', sa.String(length=5), nullable=True),
        sa.Column('proveedor', sa.String(length=200), nullable=True),
        sa.Column('dias', sa.Numeric(6, 1), nullable=False),
        sa.Column('actualizado_por', sa.Integer(), nullable=True),
        sa.Column('actualizado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            '(producto IS NOT NULL)::int + (categoria IS NOT NULL)::int + (proveedor IS NOT NULL)::int = 1',
            name='check_reabast_lead_time_un_solo_nivel',
        ),
        sa.CheckConstraint('dias > 0', name='check_reabast_lead_time_dias_positivo'),
        sa.ForeignKeyConstraint(['actualizado_por'], ['public.usuarios.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        schema='public',
    )
    op.create_index(op.f('ix_public_reabastecimiento_lead_time_id'), 'reabastecimiento_lead_time', ['id'], unique=False, schema='public')
    # 3 índices únicos PARCIALES en vez de un UniqueConstraint compuesto: en Postgres,
    # NULL nunca es igual a NULL para efectos de unicidad, así que un UNIQUE(producto,
    # categoria, proveedor) NO impediría dos filas con el mismo proveedor='ACME' mientras
    # producto/categoria sean ambos NULL en las dos -- se necesita un índice único por
    # nivel, cada uno activo solo donde ese nivel está poblado.
    op.create_index(
        'uq_reabast_lead_time_producto', 'reabastecimiento_lead_time', ['producto'],
        unique=True, schema='public', postgresql_where=sa.text('producto IS NOT NULL'),
    )
    op.create_index(
        'uq_reabast_lead_time_categoria', 'reabastecimiento_lead_time', ['categoria'],
        unique=True, schema='public', postgresql_where=sa.text('categoria IS NOT NULL'),
    )
    op.create_index(
        'uq_reabast_lead_time_proveedor', 'reabastecimiento_lead_time', ['proveedor'],
        unique=True, schema='public', postgresql_where=sa.text('proveedor IS NOT NULL'),
    )

    # ── Semilla: niveles de servicio recomendados por la auditoría 50 (D-2) ────────────
    conn = op.get_bind()
    conn.execute(sa.text(
        """
        INSERT INTO public.reabastecimiento_politica (clase_abc, nivel_servicio) VALUES
        ('A', 0.975), ('B', 0.95), ('C', 0.90)
        """
    ))
    # `reabastecimiento_lead_time` empieza vacía a propósito: el default global vive en
    # `settings.BODEGA_LEAD_TIME_DIAS` (7 días), no en una fila sintética de esta tabla
    # -- cada fila real representa una configuración específica que gerencia decidió.


def downgrade() -> None:
    op.drop_table('reabastecimiento_lead_time', schema='public')
    op.drop_table('reabastecimiento_politica', schema='public')
