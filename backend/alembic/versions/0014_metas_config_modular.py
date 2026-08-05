"""metas config modular: pipeline v3 de 16 etapas

Revision ID: 0014_metas_config_modular
Revises: 0013_motor_metas_v2
Create Date: 2026-07-31 21:00:00.000000

Fase 6 de docs/features/plan_motor_metas_v3_y_comisiones_unificadas.md: la fórmula de
metas deja de ser 13 constantes planas (`metas_config_parametros`, migración `0013`) y
pasa a un pipeline modular de 16 etapas (catálogo cerrado en
`app/services/goal_pipeline_stages.py::ETAPAS_CATALOGO`), cada una con su método, su
activación y sus parámetros en JSONB -- requisito explícito del usuario (R-9/R-10/R-12):
una fórmula "probada en otras empresas" tipo motor modular SPM (SAP/Oracle/Anaplan/
Xactly), no una fórmula fija con perillas sueltas.

`metas_config_parametros` se CONSERVA sin cambios (no se elimina, mismo criterio que
`comision_factores_credito` tras su retiro funcional en la Fase 3 de este mismo plan) --
el motor real deja de leerla, pero no se rompe ninguna herramienta de diagnóstico externa
que aún la referencie. Sus 13 valores vigentes se migran (vía `SELECT` en `upgrade`, no
hardcodeados) hacia el `parametros` JSONB de las etapas E1/E2/E3/E4/E5/E10 -- si el
entorno no tiene la semilla de `0013` aplicada (o algún valor fue editado antes de esta
migración), la semilla se usa como respaldo por clave.

Lección de la migración `0012` (mismo plan, Fase 2): nombre de revisión <= 32 caracteres
(`alembic_version.version_num VARCHAR(32)`) -- `0014_metas_config_modular` tiene 25.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0014_metas_config_modular'
down_revision: Union[str, None] = '0013_motor_metas_v2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ETAPAS_VALIDAS_SQL = (
    "'E1_limpieza','E2_nivel_base','E3_estacionalidad','E4_tendencia','E5_estabilidad',"
    "'E6_madurez','E7_estrategia','E8_tipo_vendedor','E9_capacidad','E10_restricciones',"
    "'E11_redondeo','E12_distribucion','E13_cartera','E14_potencial','E15_cumplimiento','E16_volatilidad'"
)

# Semilla de respaldo (auditoría 46, idéntica a la de la migración 0013) -- usada solo si
# la clave equivalente no existe hoy en `metas_config_parametros` en este entorno.
SEMILLA_LEGADO = {
    'ventana_referencia_outliers': 12.0, 'iqr_multiplicador': 1.5,
    'min_anios_estacional': 2.0,
    'meses_tendencia_reciente': 4.0, 'factor_tendencia_min': 0.85, 'factor_tendencia_max': 1.20,
    'cv_alto': 0.5, 'peso_estabilidad_min': 0.3,
    'banda_alcanzabilidad_min': 0.85, 'banda_alcanzabilidad_max': 1.20, 'meses_referencia_alcanzable': 6.0,
    'meses_minimos_para_iqr': 4.0,
}


def upgrade() -> None:
    op.create_table(
        'metas_config_modulos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('etapa', sa.String(length=40), nullable=False),
        sa.Column('metodo', sa.String(length=40), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=False),
        sa.Column('orden', sa.Integer(), nullable=False),
        sa.Column('parametros', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('razon_desactivacion', sa.String(length=300), nullable=True),
        sa.Column('actualizado_por', sa.Integer(), nullable=True),
        sa.Column('actualizado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(f"etapa IN ({ETAPAS_VALIDAS_SQL})", name='check_meta_config_modulo_etapa_valida'),
        sa.ForeignKeyConstraint(['actualizado_por'], ['public.usuarios.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('etapa', name='uq_metas_config_modulos_etapa'),
        schema='public',
    )
    op.create_index(op.f('ix_public_metas_config_modulos_id'), 'metas_config_modulos', ['id'], unique=False, schema='public')

    op.drop_constraint('check_tabla_auditoria_valida', 'comision_config_auditoria', schema='public', type_='check')
    op.create_check_constraint(
        'check_tabla_auditoria_valida', 'comision_config_auditoria',
        "tabla IN ('comision_matriz_categorias', 'comision_factores_credito', 'comision_config_vendedor', "
        "'comision_tramos_cobranza', 'comision_formula', 'comision_tramos_cumplimiento', 'metas_config_parametros', "
        "'metas_config_modulos')",
        schema='public',
    )

    # ── Migrar valores vigentes de metas_config_parametros hacia el JSONB por etapa ─────
    conn = op.get_bind()
    legado = dict(SEMILLA_LEGADO)
    filas = conn.execute(sa.text("SELECT clave, valor FROM public.metas_config_parametros")).fetchall()
    for clave, valor in filas:
        legado[clave] = float(valor)


    config_tbl = sa.table(
        'metas_config_modulos',
        sa.column('etapa', sa.String), sa.column('metodo', sa.String), sa.column('activo', sa.Boolean),
        sa.column('orden', sa.Integer), sa.column('parametros', postgresql.JSONB),
        sa.column('razon_desactivacion', sa.String),
    )
    op.bulk_insert(config_tbl, [
        {
            'etapa': 'E1_limpieza', 'metodo': 'tukey', 'activo': True, 'orden': 1,
            'parametros': {
                'k': legado['iqr_multiplicador'], 'ventana_referencia': legado['ventana_referencia_outliers'],
                'meses_minimos_para_iqr': legado['meses_minimos_para_iqr'],
            },
            'razon_desactivacion': None,
        },
        {
            'etapa': 'E2_nivel_base', 'metodo': 'mixto', 'activo': True, 'orden': 2,
            'parametros': {}, 'razon_desactivacion': None,
        },
        {
            'etapa': 'E3_estacionalidad', 'metodo': 'cascada', 'activo': True, 'orden': 3,
            'parametros': {'prioridad': ['propio', 'empresa'], 'min_anios_estacional': legado['min_anios_estacional']},
            'razon_desactivacion': None,
        },
        {
            'etapa': 'E4_tendencia', 'metodo': 'promedio_movil', 'activo': True, 'orden': 4,
            'parametros': {
                'ventana': legado['meses_tendencia_reciente'],
                'factor_tendencia_min': legado['factor_tendencia_min'], 'factor_tendencia_max': legado['factor_tendencia_max'],
            },
            'razon_desactivacion': None,
        },
        {
            'etapa': 'E5_estabilidad', 'metodo': 'estandar', 'activo': True, 'orden': 5,
            'parametros': {'cv_alto': legado['cv_alto'], 'peso_estabilidad_min': legado['peso_estabilidad_min']},
            'razon_desactivacion': None,
        },
        {
            'etapa': 'E6_madurez', 'metodo': 'mezcla_gradual', 'activo': True, 'orden': 6,
            'parametros': {
                'umbral_nuevo_meses': 6, 'umbral_maduro_meses': 24, 'peso_benchmark_intermedio': 0.20,
                'agrupador_benchmark': 'equipo', 'estadistico_benchmark': 'mediana',
            },
            'razon_desactivacion': None,
        },
        {
            'etapa': 'E7_estrategia', 'metodo': None, 'activo': False, 'orden': 7,
            'parametros': {'crecimiento_pct': 0.0},
            'razon_desactivacion': 'Pendiente de que gerencia defina el objetivo de crecimiento anual (§17.4 del plan).',
        },
        {
            'etapa': 'E8_tipo_vendedor', 'metodo': 'tabla', 'activo': True, 'orden': 8,
            'parametros': {'externo': 1.10, 'interno': 0.95},
            'razon_desactivacion': None,
        },
        {
            'etapa': 'E9_capacidad', 'metodo': None, 'activo': False, 'orden': 9,
            'parametros': {'holgura': 1.10},
            'razon_desactivacion': 'Cobertura de Cartera360 sin medir aún -- activar tras auditar cuántos vendedores tienen cartera identificable.',
        },
        {
            'etapa': 'E10_restricciones', 'metodo': 'banda', 'activo': True, 'orden': 10,
            'parametros': {
                'banda_alcanzabilidad_min': legado['banda_alcanzabilidad_min'],
                'banda_alcanzabilidad_max': legado['banda_alcanzabilidad_max'],
                'meses_referencia_alcanzable': legado['meses_referencia_alcanzable'],
            },
            'razon_desactivacion': None,
        },
        {
            'etapa': 'E11_redondeo', 'metodo': 'cercano', 'activo': True, 'orden': 11,
            'parametros': {'multiplo': 100}, 'razon_desactivacion': None,
        },
        {
            'etapa': 'E12_distribucion', 'metodo': None, 'activo': False, 'orden': 12,
            'parametros': {},
            'razon_desactivacion': 'Requiere una meta corporativa (public.metas_corporativas), que hoy no existe en el sistema.',
        },
        {
            'etapa': 'E13_cartera', 'metodo': None, 'activo': False, 'orden': 13,
            'parametros': {'min': 0.85, 'max': 1.15},
            'razon_desactivacion': 'Factor opcional (Fase 10) -- desactivado por defecto, requiere auditoría propia de doble conteo con reasignaciones administrativas.',
        },
        {
            'etapa': 'E14_potencial', 'metodo': None, 'activo': False, 'orden': 14,
            'parametros': {},
            'razon_desactivacion': 'Sin fuente de mercado total en el EDW -- no derivable de un ERP transaccional propio. Desactivada permanentemente.',
        },
        {
            'etapa': 'E15_cumplimiento', 'metodo': None, 'activo': False, 'orden': 15,
            'parametros': {'peso': 0.2},
            'razon_desactivacion': 'Solo julio/agosto-2026 con metas aprobadas -- se activa con >=6 meses de cumplimiento real medible (Fase 9.B).',
        },
        {
            'etapa': 'E16_volatilidad', 'metodo': None, 'activo': False, 'orden': 16,
            'parametros': {'umbral_cv': 0.40, 'factor_reduccion': 0.5},
            'razon_desactivacion': 'Se solapa con E5 (peso de estabilidad) -- desactivada por defecto para no aplicar doble penalización.',
        },
    ])


def downgrade() -> None:
    op.drop_constraint('check_tabla_auditoria_valida', 'comision_config_auditoria', schema='public', type_='check')
    op.create_check_constraint(
        'check_tabla_auditoria_valida', 'comision_config_auditoria',
        "tabla IN ('comision_matriz_categorias', 'comision_factores_credito', 'comision_config_vendedor', "
        "'comision_tramos_cobranza', 'comision_formula', 'comision_tramos_cumplimiento', 'metas_config_parametros')",
        schema='public',
    )
    op.drop_index(op.f('ix_public_metas_config_modulos_id'), table_name='metas_config_modulos', schema='public')
    op.drop_table('metas_config_modulos', schema='public')
