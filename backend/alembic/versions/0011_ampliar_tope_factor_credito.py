"""ampliar tope factor credito a 2.0

Revision ID: 0011_ampliar_tope_factor_credito
Revises: 0010_eliminar_pct_al_facturar
Create Date: 2026-07-30 14:00:00.000000

Petición explícita del usuario: el tope de `comision_factores_credito.factor` estaba en
1.5 (`check_factor_credito_valido`), insuficiente para un tramo que gerencia quiere
configurar por encima de ese valor. Se amplía a 2.0 -- el mismo constraint sigue
existiendo, solo cambia el límite superior.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0011_ampliar_tope_factor_credito'
down_revision: Union[str, None] = '0010_eliminar_pct_al_facturar'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        'check_factor_credito_valido', 'comision_factores_credito', schema='public', type_='check',
    )
    op.create_check_constraint(
        'check_factor_credito_valido', 'comision_factores_credito',
        'factor >= 0 AND factor <= 2.0', schema='public',
    )


def downgrade() -> None:
    op.drop_constraint(
        'check_factor_credito_valido', 'comision_factores_credito', schema='public', type_='check',
    )
    op.create_check_constraint(
        'check_factor_credito_valido', 'comision_factores_credito',
        'factor >= 0 AND factor <= 1.5', schema='public',
    )
