"""tokens revocados

Revision ID: 0007_tokens_revocados
Revises: 0006_usuario_almacenes
Create Date: 2026-07-30 00:00:00.000000

Denylist de tokens (auditoría 43, H43-12, docs/auditoria/43_correcciones_sesion_ventas_y_datos.md):
antes de esta migración no existía ningún mecanismo de logout del lado del servidor -- un JWT
emitido seguía siendo válido hasta su expiración natural aunque el usuario "cerrara sesión" en el
frontend. Append-only, mismo patrón que `comision_config_auditoria`/`ml_model_runs`: cada logout
explícito inserta una fila con el `jti` del token cerrado; `get_current_user` rechaza cualquier
token cuyo `jti` aparezca aquí, sin importar que la firma y el `exp` sigan siendo válidos.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0007_tokens_revocados'
down_revision: Union[str, None] = '0006_usuario_almacenes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tokens_revocados',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('jti', sa.String(length=36), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('expira_en', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revocado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['usuario_id'], ['public.usuarios.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        schema='public',
    )
    op.create_index(
        op.f('ix_public_tokens_revocados_id'), 'tokens_revocados', ['id'], unique=False, schema='public',
    )
    op.create_index(
        op.f('ix_public_tokens_revocados_jti'), 'tokens_revocados', ['jti'], unique=True, schema='public',
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_public_tokens_revocados_jti'), table_name='tokens_revocados', schema='public')
    op.drop_index(op.f('ix_public_tokens_revocados_id'), table_name='tokens_revocados', schema='public')
    op.drop_table('tokens_revocados', schema='public')
