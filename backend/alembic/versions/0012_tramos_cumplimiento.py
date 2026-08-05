"""comision tramos cumplimiento

Revision ID: 0012_tramos_cumplimiento
Revises: 0011_ampliar_tope_factor_credito
Create Date: 2026-07-31 00:00:00.000000

Auditoría 45 (docs/auditoria/45_sobrecumplimiento_umbral_y_desglose.md) + plan de
ejecución (docs/features/plan_comisiones_sobrecumplimiento_umbral_y_desglose.md):
petición explícita del usuario -- (1) un vendedor comisiona solo desde el 90% de
cumplimiento de su meta (antes el tramo 80-89% pagaba con multiplicador 0.7); (2) el
sobrecumplimiento (>100%) deja de ser un único escalón plano (1.2x sin importar cuánto
se exceda) y pasa a una escala configurable.

El multiplicador de `multiplicador_cumplimiento` (componente de la fórmula variable)
deja de resolverse desde constantes de módulo (`UMBRAL_*`/`COMISION_MULT_*`) y pasa a
una tabla con vigencia -- mismo patrón que `comision_tramos_cobranza` (migración 0008).
`perfil` admite NULL (aplica a todos los perfiles); la semilla usa un solo juego de
tramos, sin diferenciar por perfil, tal como pidió el usuario. `bono_fijo` es un monto
adicional en $ por tramo (equivalente variable de `Goal.bono_sobrecumplimiento` del
esquema plano) -- sembrado en 0.00 en todos los tramos: activarlo es decisión de
gerencia, no de esta migración.

El esquema plano legacy (`calcular_comision`, `COMISION_MODO='plana'`) NO se toca --
sigue usando sus 4 tramos fijos (`UMBRAL_EXCELENTE/META/CERCA`).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0012_tramos_cumplimiento'
down_revision: Union[str, None] = '0011_ampliar_tope_factor_credito'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'comision_tramos_cumplimiento',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('perfil', sa.String(length=15), nullable=True),
        sa.Column('pct_desde', sa.Numeric(6, 2), nullable=False),
        sa.Column('pct_hasta', sa.Numeric(6, 2), nullable=True),
        sa.Column('multiplicador', sa.Numeric(6, 4), nullable=False),
        sa.Column('etiqueta', sa.String(length=50), nullable=False),
        sa.Column('bono_fijo', sa.Numeric(12, 2), nullable=False, server_default=sa.text('0.00')),
        sa.Column('vigente_desde', sa.Date(), nullable=False),
        sa.Column('vigente_hasta', sa.Date(), nullable=True),
        sa.Column('creado_por', sa.Integer(), nullable=True),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "perfil IS NULL OR perfil IN ('externo','interno','jefe_agencia')",
            name='check_perfil_tramo_cumplimiento_valido',
        ),
        sa.CheckConstraint("pct_desde >= 0", name='check_pct_desde_valido'),
        sa.CheckConstraint("pct_hasta IS NULL OR pct_hasta > pct_desde", name='check_pct_hasta_valido'),
        sa.CheckConstraint("multiplicador >= 0", name='check_multiplicador_cumplimiento_valido'),
        sa.CheckConstraint("bono_fijo >= 0", name='check_bono_fijo_valido'),
        sa.ForeignKeyConstraint(['creado_por'], ['public.usuarios.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        schema='public',
    )
    op.create_index(
        op.f('ix_public_comision_tramos_cumplimiento_id'), 'comision_tramos_cumplimiento', ['id'],
        unique=False, schema='public',
    )

    # ── Bitácora: comision_config_auditoria gana la tabla nueva ────────────────────
    op.drop_constraint('check_tabla_auditoria_valida', 'comision_config_auditoria', schema='public', type_='check')
    op.create_check_constraint(
        'check_tabla_auditoria_valida', 'comision_config_auditoria',
        "tabla IN ('comision_matriz_categorias', 'comision_factores_credito', 'comision_config_vendedor', "
        "'comision_tramos_cobranza', 'comision_formula', 'comision_tramos_cumplimiento')",
        schema='public',
    )

    # ── Semilla: el requerimiento exacto del usuario ────────────────────────────────
    # [0,90) -> 0.0 (R-3: sin comisión bajo el 90% de la meta); [90,100) -> 1.0 (Meta);
    # escala de sobrecumplimiento 1.20/1.35/1.50 en 100/110/125% (R-1: reemplaza el
    # escalón plano 1.2x único). perfil=NULL: un solo juego de tramos para todos.
    tramos_tbl = sa.table(
        'comision_tramos_cumplimiento',
        sa.column('perfil', sa.String), sa.column('pct_desde', sa.Numeric), sa.column('pct_hasta', sa.Numeric),
        sa.column('multiplicador', sa.Numeric), sa.column('etiqueta', sa.String),
        sa.column('bono_fijo', sa.Numeric), sa.column('vigente_desde', sa.Date),
    )
    hoy = '1900-01-01'
    op.bulk_insert(tramos_tbl, [
        {'perfil': None, 'pct_desde': 0, 'pct_hasta': 90, 'multiplicador': 0.0000, 'etiqueta': 'Sin comisión (< 90% de la meta)', 'bono_fijo': 0.00, 'vigente_desde': hoy},
        {'perfil': None, 'pct_desde': 90, 'pct_hasta': 100, 'multiplicador': 1.0000, 'etiqueta': 'Meta', 'bono_fijo': 0.00, 'vigente_desde': hoy},
        {'perfil': None, 'pct_desde': 100, 'pct_hasta': 110, 'multiplicador': 1.2000, 'etiqueta': 'Sobrecumplimiento', 'bono_fijo': 0.00, 'vigente_desde': hoy},
        {'perfil': None, 'pct_desde': 110, 'pct_hasta': 125, 'multiplicador': 1.3500, 'etiqueta': 'Sobrecumplimiento alto', 'bono_fijo': 0.00, 'vigente_desde': hoy},
        {'perfil': None, 'pct_desde': 125, 'pct_hasta': None, 'multiplicador': 1.5000, 'etiqueta': 'Excelencia', 'bono_fijo': 0.00, 'vigente_desde': hoy},
    ])


def downgrade() -> None:
    op.drop_constraint('check_tabla_auditoria_valida', 'comision_config_auditoria', schema='public', type_='check')
    op.create_check_constraint(
        'check_tabla_auditoria_valida', 'comision_config_auditoria',
        "tabla IN ('comision_matriz_categorias', 'comision_factores_credito', 'comision_config_vendedor', "
        "'comision_tramos_cobranza', 'comision_formula')",
        schema='public',
    )
    op.drop_index(
        op.f('ix_public_comision_tramos_cumplimiento_id'), table_name='comision_tramos_cumplimiento', schema='public',
    )
    op.drop_table('comision_tramos_cumplimiento', schema='public')
