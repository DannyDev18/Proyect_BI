"""quitar public.anomalias_revisiones (decomisión del modelo anomaly)

Revision ID: 0018_quitar_anomalias
Revises: 0017_propuesta_compra
Create Date: 2026-08-04 00:00:00.000000

Decomisión completa del modelo `anomaly` (Isolation Forest), petición explícita del
usuario -- mismo criterio que sales_rf/goals_rf (docs/auditoria/49_.../20_...): se
retira de punta a punta, no solo se oculta en el frontend. `public.anomalias_revisiones`
(cola de triage del panel de Administrador, creada en la baseline `0001`) pierde su
único consumidor real (`AnomaliaRevisionService`, `GET/PATCH /admin/anomalies*`, ya
eliminados del código) y se elimina en vez de dejarse huérfana.

Ver docs/auditoria/51_decomision_anomaly_y_churn_unico.md.

Nombre de revisión <= 32 caracteres: '0018_quitar_anomalias' tiene 22.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0018_quitar_anomalias'
down_revision: Union[str, None] = '0017_propuesta_compra'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(op.f('ix_public_anomalias_revisiones_transaccion_id'), table_name='anomalias_revisiones', schema='public')
    op.drop_index(op.f('ix_public_anomalias_revisiones_id'), table_name='anomalias_revisiones', schema='public')
    op.drop_index(op.f('ix_public_anomalias_revisiones_estado'), table_name='anomalias_revisiones', schema='public')
    op.drop_table('anomalias_revisiones', schema='public')


def downgrade() -> None:
    op.create_table(
        'anomalias_revisiones',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('transaccion_id', sa.String(length=50), nullable=False),
        sa.Column('score', sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column('estado', sa.String(length=20), nullable=False),
        sa.Column('revisor_id', sa.Integer(), nullable=True),
        sa.Column('nota', sa.Text(), nullable=True),
        sa.Column('fecha_deteccion', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('fecha_revision', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("estado IN ('nueva', 'revisada', 'descartada', 'confirmada')", name='check_estado_revision_valido'),
        sa.ForeignKeyConstraint(['revisor_id'], ['public.usuarios.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        schema='public',
    )
    op.create_index(op.f('ix_public_anomalias_revisiones_estado'), 'anomalias_revisiones', ['estado'], unique=False, schema='public')
    op.create_index(op.f('ix_public_anomalias_revisiones_id'), 'anomalias_revisiones', ['id'], unique=False, schema='public')
    op.create_index(op.f('ix_public_anomalias_revisiones_transaccion_id'), 'anomalias_revisiones', ['transaccion_id'], unique=True, schema='public')
