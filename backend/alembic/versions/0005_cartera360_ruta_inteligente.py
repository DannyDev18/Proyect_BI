"""cartera360 ruta inteligente

Revision ID: 0005_cartera360_ruta_inteligente
Revises: 0004_ml_model_runs
Create Date: 2026-07-28 00:00:00.000000

Fase 1 de docs/features/plan_refactor_cartera360_ruta_inteligente.md (§2.3, §7 Estrategia
de migración): 100% aditivo, sin ruptura. `gestion_cartera_eventos` gana 4 columnas
nullable (`canal`, `resultado`, `proxima_accion_fecha`, `nota`) y su CHECK de `evento` se
amplía de 3 a 8 valores (nunca se restringe -- riesgo R-4). Tabla nueva
`cartera_recordatorios`. Ventana ideal para el cambio de esquema: la tabla tenía 0 filas
al momento de escribir este plan (D-1, docs/auditoria/41_reconciliacion_...md confirma que
sigue sin telemetría acumulada por Fase 0 de este refactor).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0005_cartera360_ruta_inteligente'
down_revision: Union[str, None] = '0004_ml_model_runs'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # evento pasa de varchar(20) a varchar(30): el valor más largo agregado
    # ('interesado_sin_cierre', 21 caracteres) ya no cabe en 20.
    op.alter_column(
        'gestion_cartera_eventos', 'evento', type_=sa.String(length=30), schema='public',
    )
    # gestion_cartera_eventos: +4 columnas nullable, CHECK ampliado (evento) + CHECK nuevo (canal)
    op.add_column('gestion_cartera_eventos', sa.Column('canal', sa.String(length=20), nullable=True), schema='public')
    op.add_column('gestion_cartera_eventos', sa.Column('resultado', sa.Text(), nullable=True), schema='public')
    op.add_column('gestion_cartera_eventos', sa.Column('proxima_accion_fecha', sa.Date(), nullable=True), schema='public')
    op.add_column('gestion_cartera_eventos', sa.Column('nota', sa.Text(), nullable=True), schema='public')

    op.drop_constraint('check_gestion_evento_valido', 'gestion_cartera_eventos', schema='public', type_='check')
    op.create_check_constraint(
        'check_gestion_evento_valido',
        'gestion_cartera_eventos',
        "evento IN ('contactado', 'recompro', 'perdido', 'no_contesto', 'reagendado', "
        "'interesado_sin_cierre', 'objecion_precio', 'objecion_stock')",
        schema='public',
    )
    op.create_check_constraint(
        'check_gestion_canal_valido',
        'gestion_cartera_eventos',
        "canal IS NULL OR canal IN ('llamada', 'whatsapp', 'email', 'visita')",
        schema='public',
    )

    # cartera_recordatorios: tabla nueva
    op.create_table(
        'cartera_recordatorios',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('cliente_sk', sa.Integer(), nullable=False),
        sa.Column('fecha_programada', sa.Date(), nullable=False),
        sa.Column('nota', sa.Text(), nullable=True),
        sa.Column('estado', sa.String(length=20), nullable=False, server_default='pendiente'),
        sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('cumplido_en', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['usuario_id'], ['public.usuarios.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("estado IN ('pendiente', 'cumplido', 'vencido')", name='check_recordatorio_estado_valido'),
        schema='public',
    )
    op.create_index(
        op.f('ix_public_cartera_recordatorios_id'), 'cartera_recordatorios', ['id'], unique=False, schema='public',
    )
    op.create_index(
        op.f('ix_public_cartera_recordatorios_usuario_id'), 'cartera_recordatorios', ['usuario_id'],
        unique=False, schema='public',
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_public_cartera_recordatorios_usuario_id'), table_name='cartera_recordatorios', schema='public',
    )
    op.drop_index(op.f('ix_public_cartera_recordatorios_id'), table_name='cartera_recordatorios', schema='public')
    op.drop_table('cartera_recordatorios', schema='public')

    op.drop_constraint('check_gestion_canal_valido', 'gestion_cartera_eventos', schema='public', type_='check')
    op.drop_constraint('check_gestion_evento_valido', 'gestion_cartera_eventos', schema='public', type_='check')
    op.create_check_constraint(
        'check_gestion_evento_valido',
        'gestion_cartera_eventos',
        "evento IN ('contactado', 'recompro', 'perdido')",
        schema='public',
    )

    op.drop_column('gestion_cartera_eventos', 'nota', schema='public')
    op.drop_column('gestion_cartera_eventos', 'proxima_accion_fecha', schema='public')
    op.drop_column('gestion_cartera_eventos', 'resultado', schema='public')
    op.drop_column('gestion_cartera_eventos', 'canal', schema='public')
    op.alter_column('gestion_cartera_eventos', 'evento', type_=sa.String(length=20), schema='public')
