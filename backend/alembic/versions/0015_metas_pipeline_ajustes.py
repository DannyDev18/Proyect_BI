"""metas pipeline v3: retira E12/E14 (nunca implementables) del catalogo

Revision ID: 0015_metas_pipeline_ajustes
Revises: 0014_metas_config_modular
Create Date: 2026-08-04 10:00:00.000000

Petición explícita del usuario sobre el panel "Fórmula de metas": "quitar todo lo que no
tiene un efecto en la regla de las metas ya que no quiero que solo este de forma de
mockup". E12 (distribución corporativa) y E14 (potencial de mercado) nunca tuvieron un
método `implementado=True` en `goal_pipeline_stages.ETAPAS_CATALOGO` -- E12 requiere
`public.metas_corporativas` (tabla inexistente) y E14 requiere una fuente de mercado
total que ningún ERP transaccional propio puede proveer. Dejarlas en el catálogo/UI era
mostrar una tarjeta de configuración que NUNCA podía activarse -- exactamente el mockup
que el usuario pidió eliminar. Se borran sus filas y se retiran del CHECK cerrado de
`etapa`; si en el futuro gerencia define un objetivo corporativo real, E12 se
reintroduce con su propia migración cuando la tabla exista.

Lección de las migraciones `0012`/`0014` (mismo plan): nombre de revisión <= 32
caracteres (`alembic_version.version_num VARCHAR(32)`) -- `0015_metas_pipeline_ajustes`
tiene 28.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0015_metas_pipeline_ajustes'
down_revision: Union[str, None] = '0014_metas_config_modular'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ETAPAS_VALIDAS_SQL_SIN_E12_E14 = (
    "'E1_limpieza','E2_nivel_base','E3_estacionalidad','E4_tendencia','E5_estabilidad',"
    "'E6_madurez','E7_estrategia','E8_tipo_vendedor','E9_capacidad','E10_restricciones',"
    "'E11_redondeo','E13_cartera','E15_cumplimiento','E16_volatilidad'"
)

ETAPAS_VALIDAS_SQL_CON_E12_E14 = (
    "'E1_limpieza','E2_nivel_base','E3_estacionalidad','E4_tendencia','E5_estabilidad',"
    "'E6_madurez','E7_estrategia','E8_tipo_vendedor','E9_capacidad','E10_restricciones',"
    "'E11_redondeo','E12_distribucion','E13_cartera','E14_potencial','E15_cumplimiento','E16_volatilidad'"
)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        "DELETE FROM public.metas_config_modulos WHERE etapa IN ('E12_distribucion', 'E14_potencial')"
    ))
    op.drop_constraint('check_meta_config_modulo_etapa_valida', 'metas_config_modulos', schema='public', type_='check')
    op.create_check_constraint(
        'check_meta_config_modulo_etapa_valida', 'metas_config_modulos',
        f"etapa IN ({ETAPAS_VALIDAS_SQL_SIN_E12_E14})",
        schema='public',
    )


def downgrade() -> None:
    op.drop_constraint('check_meta_config_modulo_etapa_valida', 'metas_config_modulos', schema='public', type_='check')
    op.create_check_constraint(
        'check_meta_config_modulo_etapa_valida', 'metas_config_modulos',
        f"etapa IN ({ETAPAS_VALIDAS_SQL_CON_E12_E14})",
        schema='public',
    )
    conn = op.get_bind()
    conn.execute(sa.text(
        """
        INSERT INTO public.metas_config_modulos (etapa, metodo, activo, orden, parametros, razon_desactivacion)
        VALUES
        ('E12_distribucion', NULL, FALSE, 12, '{}'::jsonb,
         'Requiere una meta corporativa (public.metas_corporativas), que hoy no existe en el sistema.'),
        ('E14_potencial', NULL, FALSE, 14, '{}'::jsonb,
         'Sin fuente de mercado total en el EDW -- no derivable de un ERP transaccional propio. Desactivada permanentemente.')
        """
    ))
