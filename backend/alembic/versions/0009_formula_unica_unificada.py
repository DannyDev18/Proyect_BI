"""formula unica unificada

Revision ID: 0009_formula_unica_unificada
Revises: 0008_comisiones_cobranza
Create Date: 2026-07-30 12:00:00.000000

Corrección de diseño (auditoría 44, petición explícita del usuario tras revisar la
Fase 4): "las comisiones variables son un todo" -- líneas de venta (margen/categoría)
y cobranza (por tramo de días de cobro) NO son dos esquemas entre los que gerencia
"activa" uno u otro; se SUMAN en una sola comisión por vendedor. La migración 0008
sembró dos fórmulas alternativas ('actual' / 'cobranza') pensadas para activarse una a
la vez -- este cambio las consolida en UNA SOLA fórmula con los 7 componentes (líneas
de venta, cobranza, contado de agencia, factor de tipo, cumplimiento, devoluciones,
bonos), todos sumados/combinados según corresponde. El simulador
(`CommissionSimulationService`) y el cálculo real (`CommissionService`) ahora comparten
el mismo motor (`commission_variable_engine.calcular_comision_variable_completa`) y
leen esta única fórmula -- no queda ningún concepto de "elegir" entre fórmulas."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0009_formula_unica_unificada'
down_revision: Union[str, None] = '0008_comisiones_cobranza'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Borra la fórmula alternativa 'cobranza' (cascade elimina sus 4 componentes).
    conn.execute(sa.text("DELETE FROM public.comision_formula WHERE clave = 'cobranza'"))

    # Renombra 'actual' -> 'variable' (deja de tener sentido "la actual" cuando ya no
    # hay una segunda fórmula entre la cual elegir) y reemplaza su tubería completa por
    # los 7 componentes unificados, en el orden correcto: las 3 bases se SUMAN primero,
    # luego se multiplica el total por factor de tipo y por cumplimiento, y al final se
    # resta la devolución y se suma el bono.
    conn.execute(sa.text(
        "UPDATE public.comision_formula SET clave = 'variable', "
        "nombre = 'Comisión Variable (todas las configuraciones)' WHERE clave = 'actual'"
    ))
    formula_id = conn.execute(
        sa.text("SELECT id FROM public.comision_formula WHERE clave = 'variable'")
    ).scalar()

    conn.execute(sa.text(
        "DELETE FROM public.comision_formula_componente WHERE formula_id = :fid"
    ), {"fid": formula_id})

    componentes = [
        (1, "base_lineas_venta", "sumar"),
        (2, "base_cobranza", "sumar"),
        (3, "contado_agencia", "sumar"),
        (4, "factor_tipo_vendedor", "multiplicar"),
        (5, "multiplicador_cumplimiento", "multiplicar"),
        (6, "devoluciones", "restar"),
        (7, "bonos", "sumar"),
    ]
    for orden, componente, operador in componentes:
        conn.execute(sa.text(
            "INSERT INTO public.comision_formula_componente "
            "(formula_id, orden, componente, operador, activo, parametros) "
            "VALUES (:fid, :orden, :componente, :operador, true, '{}'::jsonb)"
        ), {"fid": formula_id, "orden": orden, "componente": componente, "operador": operador})


def downgrade() -> None:
    conn = op.get_bind()
    formula_id = conn.execute(
        sa.text("SELECT id FROM public.comision_formula WHERE clave = 'variable'")
    ).scalar()
    if formula_id is not None:
        conn.execute(sa.text(
            "DELETE FROM public.comision_formula_componente WHERE formula_id = :fid"
        ), {"fid": formula_id})
        conn.execute(sa.text(
            "UPDATE public.comision_formula SET clave = 'actual', "
            "nombre = 'Margen/categoría (esquema vigente)' WHERE id = :fid"
        ), {"fid": formula_id})
        for orden, componente, operador in [
            (1, "base_lineas_venta", "sumar"),
            (2, "factor_tipo_vendedor", "multiplicar"),
            (3, "multiplicador_cumplimiento", "multiplicar"),
            (4, "devoluciones", "restar"),
            (5, "bonos", "sumar"),
        ]:
            conn.execute(sa.text(
                "INSERT INTO public.comision_formula_componente "
                "(formula_id, orden, componente, operador, activo, parametros) "
                "VALUES (:fid, :orden, :componente, :operador, true, '{}'::jsonb)"
            ), {"fid": formula_id, "orden": orden, "componente": componente, "operador": operador})

    id_cobranza = conn.execute(
        sa.text(
            "INSERT INTO public.comision_formula (clave, nombre, activa) "
            "VALUES ('cobranza', 'Comisión sobre cobros + contado de agencia', false) RETURNING id"
        )
    ).scalar()
    for orden, componente, operador in [
        (1, "base_cobranza", "sumar"),
        (2, "contado_agencia", "sumar"),
        (3, "devoluciones", "restar"),
        (4, "bonos", "sumar"),
    ]:
        conn.execute(sa.text(
            "INSERT INTO public.comision_formula_componente "
            "(formula_id, orden, componente, operador, activo, parametros) "
            "VALUES (:fid, :orden, :componente, :operador, true, '{}'::jsonb)"
        ), {"fid": id_cobranza, "orden": orden, "componente": componente, "operador": operador})
