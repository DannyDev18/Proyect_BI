"""comision config auditoria

Revision ID: 0003_comision_config_auditoria
Revises: 0002_seed_roles
Create Date: 2026-07-16 16:00:11.671016

Bitácora append-only de cambios a la configuración de Comisiones Variables (matriz de
categorías, factores de crédito, tipo de vendedor) -- Fase 2 ítem 2 de
docs/features/plan_actualizacion_modulo_metas_comisiones.md §3. Generada con
`alembic revision --autogenerate` contra una BD ya en `head` y recortada a mano a solo
el `create_table`/`create_index` de la tabla nueva -- el resto del diff que autogenerate
propuso es el ruido de FK conocido y documentado en `alembic/env.py` (ver auditoría 37).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0003_comision_config_auditoria'
down_revision: Union[str, None] = '0002_seed_roles'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'comision_config_auditoria',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('tabla', sa.String(length=50), nullable=False),
        sa.Column('accion', sa.String(length=20), nullable=False),
        sa.Column('detalle_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "tabla IN ('comision_matriz_categorias', 'comision_factores_credito', 'comision_config_vendedor')",
            name='check_tabla_auditoria_valida',
        ),
        sa.ForeignKeyConstraint(['usuario_id'], ['public.usuarios.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        schema='public',
    )
    op.create_index(
        op.f('ix_public_comision_config_auditoria_id'), 'comision_config_auditoria', ['id'],
        unique=False, schema='public',
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_public_comision_config_auditoria_id'), table_name='comision_config_auditoria', schema='public')
    op.drop_table('comision_config_auditoria', schema='public')
