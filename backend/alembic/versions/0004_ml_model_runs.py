"""ml model runs

Revision ID: 0004_ml_model_runs
Revises: 0003_comision_config_auditoria
Create Date: 2026-07-20 16:30:00.000000

Bitácora append-only de corridas de reentrenamiento con gating (Fase 3,
docs/features/plan_mejora_pipeline_ml.md §5.1). El proceso `ml` (contenedor separado,
misma base de datos Postgres) escribe una fila por cada intento de reentrenamiento --
promovido o rechazado -- con ambas métricas (candidato vs. campeón anterior). Mismo
patrón append-only que `comision_config_auditoria` (migración 0003).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0004_ml_model_runs'
down_revision: Union[str, None] = '0003_comision_config_auditoria'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ml_model_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('clave', sa.String(length=30), nullable=False),
        sa.Column('version_candidato', sa.String(length=20), nullable=False),
        sa.Column('version_campeon_anterior', sa.String(length=20), nullable=True),
        sa.Column('promovido', sa.Boolean(), nullable=False),
        sa.Column('metrica_nombre', sa.String(length=50), nullable=True),
        sa.Column('metrica_candidato', sa.Float(), nullable=True),
        sa.Column('metrica_campeon_anterior', sa.Float(), nullable=True),
        sa.Column('razon', sa.Text(), nullable=False),
        sa.Column('metrics_candidato', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('metrics_campeon_anterior', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('disparado_por', sa.String(length=20), nullable=False, server_default='manual'),
        sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        schema='public',
    )
    op.create_index(
        op.f('ix_public_ml_model_runs_id'), 'ml_model_runs', ['id'], unique=False, schema='public',
    )
    op.create_index(
        op.f('ix_public_ml_model_runs_clave'), 'ml_model_runs', ['clave'], unique=False, schema='public',
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_public_ml_model_runs_clave'), table_name='ml_model_runs', schema='public')
    op.drop_index(op.f('ix_public_ml_model_runs_id'), table_name='ml_model_runs', schema='public')
    op.drop_table('ml_model_runs', schema='public')
