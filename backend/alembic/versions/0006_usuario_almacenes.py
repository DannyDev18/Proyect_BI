"""usuario almacenes N:N

Revision ID: 0006_usuario_almacenes
Revises: 0005_cartera360_ruta_inteligente
Create Date: 2026-07-29 00:00:00.000000

Fase 1.a de docs/features/plan_correcciones_integrales_sistema.md (B-2): reemplaza el
modelo 1:1 `usuarios.codalm` (una bodega o NULL = "todas") por una relación N:N --
decisión del usuario (2026-07-29), corrigiendo una respuesta previa: "un usuario puede
ver varias bodegas y otro usuario puede ver solo su bodega, esto depende de cómo lo creó
el admin". `todos_los_almacenes` es una columna real (no se infiere del conjunto vacío)
porque con N:N el conjunto vacío es ambiguo entre "sin asignar" y "todas"; dejar esa
ambigüedad sin resolver arriesgaría un alta que vea todo el sistema por defecto.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0006_usuario_almacenes'
down_revision: Union[str, None] = '0005_cartera360_ruta_inteligente'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'usuarios',
        sa.Column('todos_los_almacenes', sa.Boolean(), nullable=False, server_default=sa.false()),
        schema='public',
    )

    op.create_table(
        'usuario_almacenes',
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('codalm', sa.String(length=10), nullable=False),
        sa.ForeignKeyConstraint(['usuario_id'], ['public.usuarios.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('usuario_id', 'codalm'),
        schema='public',
    )

    # Backfill (B-2): codalm no nulo -> una fila en la tabla nueva; codalm NULL con rol
    # bodega -> todos_los_almacenes=TRUE (mismo significado que tenía NULL antes).
    op.execute(
        "INSERT INTO public.usuario_almacenes (usuario_id, codalm) "
        "SELECT id, codalm FROM public.usuarios WHERE codalm IS NOT NULL"
    )
    op.execute(
        "UPDATE public.usuarios u SET todos_los_almacenes = TRUE "
        "FROM public.roles r "
        "WHERE u.rol_id = r.id AND r.nombre = 'bodega' AND u.codalm IS NULL"
    )

    op.drop_column('usuarios', 'codalm', schema='public')


def downgrade() -> None:
    op.add_column('usuarios', sa.Column('codalm', sa.String(length=10), nullable=True), schema='public')
    # Downgrade con pérdida de información declarada: el modelo 1:1 no puede representar
    # "varias bodegas" -- se conserva solo la primera asignación de cada usuario.
    op.execute(
        "UPDATE public.usuarios u SET codalm = ("
        "SELECT ua.codalm FROM public.usuario_almacenes ua "
        "WHERE ua.usuario_id = u.id ORDER BY ua.codalm LIMIT 1)"
    )
    op.drop_table('usuario_almacenes', schema='public')
    op.drop_column('usuarios', 'todos_los_almacenes', schema='public')
