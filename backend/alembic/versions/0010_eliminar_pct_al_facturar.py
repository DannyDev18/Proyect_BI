"""eliminar pct_al_facturar

Revision ID: 0010_eliminar_pct_al_facturar
Revises: 0009_formula_unica_unificada
Create Date: 2026-07-30 13:00:00.000000

`comision_factores_credito.pct_al_facturar` se reservó en la migración 0001 para una
fase futura ("split anticipo al facturar vs. al cobrar") que nunca se implementó en el
motor real (`commission_engine.calcular_base_lineas_venta` nunca la lee) -- el frontend
ya la marcaba explícitamente "no usado aún". Petición explícita del usuario: esa
necesidad (dividir la comisión entre el momento de facturar y el momento de cobrar) ya
la resuelve, con datos reales, la Comisión sobre Cobros (`comision_tramos_cobranza` +
componente `base_cobranza` de la fórmula unificada, migración 0009) -- mantener el campo
sería un placeholder muerto y redundante. Se elimina por completo en vez de dejarlo como
vestigio, siguiendo la convención del proyecto de no mantener campos sin uso real.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0010_eliminar_pct_al_facturar'
down_revision: Union[str, None] = '0009_formula_unica_unificada'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('comision_factores_credito', 'pct_al_facturar', schema='public')


def downgrade() -> None:
    op.add_column(
        'comision_factores_credito',
        sa.Column('pct_al_facturar', sa.Numeric(precision=5, scale=2), nullable=False, server_default='100.0'),
        schema='public',
    )
