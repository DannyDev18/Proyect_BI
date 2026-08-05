"""motor metas v2: trazabilidad y parametros configurables

Revision ID: 0013_motor_metas_v2
Revises: 0012_tramos_cumplimiento
Create Date: 2026-07-31 12:00:00.000000

Auditoría 46 (docs/auditoria/46_motor_metas_configurable.md) + plan de ejecución
(docs/features/plan_motor_metas_configurable.md): petición explícita del usuario --
(1) hacer editable/manejable por el gerente la fórmula de la meta (hoy 13 constantes de
módulo en Python); (2) que "ver cómo se calculó" muestre los valores REALES que
produjeron la meta guardada, no un recálculo con la configuración de hoy (H-5, auditoría
46: confirmado con un caso real -- VEN13/agosto-2026 difiere 58% entre la meta persistida
y lo que el motor recalcula hoy, sin forma de reconstruir la diferencia).

`metas_comerciales_operativas` gana `trazabilidad_calculo` (JSONB, NULL en metas
generadas antes de esta migración). `metas_config_parametros` es una fila viva por
clave (sin vigencia histórica -- ver docstring de `app/models/meta_config.py` para la
diferencia deliberada con `comision_tramos_cumplimiento`), sembrada con la semilla
validada en la auditoría 46 (ventana 36 meses, banda de alcanzabilidad 0.85-1.20, etc.)
para que la primera versión ya sea la configuración recomendada, no un placeholder.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0013_motor_metas_v2'
down_revision: Union[str, None] = '0012_tramos_cumplimiento'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'metas_comerciales_operativas',
        sa.Column('trazabilidad_calculo', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema='public',
    )

    op.create_table(
        'metas_config_parametros',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('clave', sa.String(length=60), nullable=False),
        sa.Column('valor', sa.Numeric(10, 4), nullable=False),
        sa.Column('descripcion', sa.String(length=300), nullable=True),
        sa.Column('actualizado_por', sa.Integer(), nullable=True),
        sa.Column('actualizado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('valor > 0', name='check_meta_config_valor_positivo'),
        sa.ForeignKeyConstraint(['actualizado_por'], ['public.usuarios.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('clave', name='uq_metas_config_parametros_clave'),
        schema='public',
    )
    op.create_index(
        op.f('ix_public_metas_config_parametros_id'), 'metas_config_parametros', ['id'],
        unique=False, schema='public',
    )

    # ── Bitácora: comision_config_auditoria gana la tabla nueva (bitácora genérica de
    # cambios de configuración, ya reutilizada por 4 tablas previas) ────────────────
    op.drop_constraint('check_tabla_auditoria_valida', 'comision_config_auditoria', schema='public', type_='check')
    op.create_check_constraint(
        'check_tabla_auditoria_valida', 'comision_config_auditoria',
        "tabla IN ('comision_matriz_categorias', 'comision_factores_credito', 'comision_config_vendedor', "
        "'comision_tramos_cobranza', 'comision_formula', 'comision_tramos_cumplimiento', 'metas_config_parametros')",
        schema='public',
    )

    # ── Semilla: reproduce la configuración recomendada por la auditoría 46 ─────────
    config_tbl = sa.table(
        'metas_config_parametros',
        sa.column('clave', sa.String), sa.column('valor', sa.Numeric), sa.column('descripcion', sa.String),
    )
    op.bulk_insert(config_tbl, [
        {'clave': 'ventana_meses', 'valor': 36, 'descripcion': 'Meses de histórico usados como ventana de cálculo.'},
        {'clave': 'ventana_referencia_outliers', 'valor': 12, 'descripcion': 'Meses recientes sobre los que se calculan los cuartiles de Tukey.'},
        {'clave': 'iqr_multiplicador', 'valor': 1.5, 'descripcion': 'Multiplicador de Tukey para las bandas de outliers (1.5 = estándar).'},
        {'clave': 'min_anios_estacional', 'valor': 2, 'descripcion': 'Años mínimos del mismo mes calendario para un índice estacional propio del vendedor.'},
        {'clave': 'meses_tendencia_reciente', 'valor': 4, 'descripcion': 'Meses recientes usados para el factor de tendencia.'},
        {'clave': 'factor_tendencia_min', 'valor': 0.85, 'descripcion': 'Piso del factor de tendencia (crecimiento/decrecimiento acotado).'},
        {'clave': 'factor_tendencia_max', 'valor': 1.20, 'descripcion': 'Techo del factor de tendencia.'},
        {'clave': 'cv_alto', 'valor': 0.5, 'descripcion': 'Coeficiente de variación a partir del cual se atenúa el efecto de la tendencia.'},
        {'clave': 'peso_estabilidad_min', 'valor': 0.3, 'descripcion': 'Piso del peso de estabilidad (nunca se anula del todo el efecto de la tendencia).'},
        {'clave': 'banda_alcanzabilidad_min', 'valor': 0.85, 'descripcion': 'Piso de la meta final, como fracción de la referencia alcanzable reciente.'},
        {'clave': 'banda_alcanzabilidad_max', 'valor': 1.20, 'descripcion': 'Techo de la meta final, como fracción de la referencia alcanzable reciente.'},
        {'clave': 'meses_referencia_alcanzable', 'valor': 6, 'descripcion': 'Meses recientes usados para calcular la referencia de alcanzabilidad (mediana).'},
        {'clave': 'meses_minimos_para_iqr', 'valor': 4, 'descripcion': 'Meses mínimos de histórico para tener resolución estadística de outliers.'},
    ])


def downgrade() -> None:
    op.drop_constraint('check_tabla_auditoria_valida', 'comision_config_auditoria', schema='public', type_='check')
    op.create_check_constraint(
        'check_tabla_auditoria_valida', 'comision_config_auditoria',
        "tabla IN ('comision_matriz_categorias', 'comision_factores_credito', 'comision_config_vendedor', "
        "'comision_tramos_cobranza', 'comision_formula', 'comision_tramos_cumplimiento')",
        schema='public',
    )
    op.drop_index(op.f('ix_public_metas_config_parametros_id'), table_name='metas_config_parametros', schema='public')
    op.drop_table('metas_config_parametros', schema='public')
    op.drop_column('metas_comerciales_operativas', 'trazabilidad_calculo', schema='public')
