"""reabastecimiento: propuestas de compra persistidas (F9)

Revision ID: 0017_propuesta_compra
Revises: 0016_reabastecimiento
Create Date: 2026-08-04 15:00:00.000000

F9 de docs/features/plan_reabastecimiento_inteligente.md (bloque 5, Gestión Operativa):
cierra la brecha explícita dejada en la migración 0016 -- convierte la recomendación
calculada al vuelo en una decisión de negocio persistida y auditable.

- `propuesta_compra`: cabecera. Estado `borrador|aprobada|rechazada|exportada`,
  usuario que la generó, filtros de origen (JSONB, para saber el alcance sin
  adivinar), horizonte y total.
- `propuesta_compra_linea`: línea por artículo con SNAPSHOT congelado de la
  justificación (mismo criterio que `comision_liquidaciones`: una propuesta ya creada
  no se recalcula al mirarla -- aprobar/rechazar es sobre lo que el usuario vio, no
  sobre un número que cambió mientras decidía).

`transferencia_decision` (cierre de H-5, aprobación de transferencias hoy en `useState`
efímero de `BodegaAlmacenes.tsx`) queda fuera de esta migración -- pertenece a un router/
página distintos (`warehouse.py`/`BodegaAlmacenes.tsx`, no `replenishment.py`/
`BodegaReabastecimiento.tsx`) y se documenta como trabajo de seguimiento, no una omisión
silenciosa (ver docs/auditoria/50_reabastecimiento_inteligente.md).

Nombre de revisión <= 32 caracteres: '0017_propuesta_compra' tiene 22.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0017_propuesta_compra'
down_revision: Union[str, None] = '0016_reabastecimiento'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'propuesta_compra',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('estado', sa.String(length=20), nullable=False, server_default='borrador'),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('filtros_origen', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('horizonte_dias', sa.Numeric(6, 1), nullable=False),
        sa.Column('total', sa.Numeric(14, 2), nullable=False, server_default='0'),
        sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('actualizado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "estado IN ('borrador', 'aprobada', 'rechazada', 'exportada')",
            name='check_propuesta_compra_estado_valido',
        ),
        sa.ForeignKeyConstraint(['usuario_id'], ['public.usuarios.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        schema='public',
    )
    op.create_index(op.f('ix_public_propuesta_compra_id'), 'propuesta_compra', ['id'], unique=False, schema='public')

    op.create_table(
        'propuesta_compra_linea',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('propuesta_id', sa.Integer(), nullable=False),
        sa.Column('codart', sa.String(length=50), nullable=False),
        sa.Column('nombre', sa.String(length=200), nullable=False),
        sa.Column('cantidad', sa.Numeric(12, 2), nullable=False),
        sa.Column('costo_unitario', sa.Numeric(12, 4), nullable=False),
        sa.Column('costo_total', sa.Numeric(14, 2), nullable=False),
        sa.Column('justificacion', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.ForeignKeyConstraint(['propuesta_id'], ['public.propuesta_compra.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        schema='public',
    )
    op.create_index(
        op.f('ix_public_propuesta_compra_linea_id'), 'propuesta_compra_linea', ['id'], unique=False, schema='public',
    )
    op.create_index(
        op.f('ix_public_propuesta_compra_linea_propuesta_id'), 'propuesta_compra_linea', ['propuesta_id'],
        unique=False, schema='public',
    )


def downgrade() -> None:
    op.drop_table('propuesta_compra_linea', schema='public')
    op.drop_table('propuesta_compra', schema='public')
