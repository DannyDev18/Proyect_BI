"""baseline public schema

Revision ID: 0001_baseline_public
Revises:
Create Date: 2026-07-16 14:44:52.938117

Crea las 12 tablas modeladas de `public` (`app/database/base.py`) con DDL congelado --
generado una sola vez con `alembic revision --autogenerate` comparando `Base.metadata`
contra un Postgres vacío, y pegado aquí a mano (docs/auditoria/37_migraciones_esquema_public.md).

Es DELIBERADO que este archivo NO delegue en `Base.metadata.create_all` en tiempo de
ejecución: se probó esa vía primero y expone un bug real -- como usa la metadata VIVA,
cualquier columna que alguien agregue a un modelo aparecería automáticamente en
instalaciones nuevas sin necesitar ninguna migración nueva, mientras que una BD ya
migrada a `head` nunca la recibiría (0001 ya corrió, no se re-ejecuta). Esto rompe la
premisa central de Alembic: mismo `alembic upgrade head` -> mismo esquema, sin importar
el punto de partida. Con DDL congelado, un cambio de modelo sin una migración nueva
correspondiente HACE FALLAR el test de guardia
(`tests/integration/test_alembic_schema_sync.py`) en vez de colarse en silencio.

Fuera de `Base.metadata` van dos objetos que Alembic no reconoce como "tabla
modelada" y que se crean con SQL crudo:
  - `public.cliente_lookup`: sin modelo SQLAlchemy (el ETL escribe ahí directo, nunca
    el backend) -- `alembic/env.py::include_object` la excluye explícitamente para que
    ningún `--autogenerate` futuro la proponga como huérfana.
  - `public.set_updated_at()` + el trigger que dispara sobre `public.usuarios`: los
    triggers/funciones no son objetos de `Table`, Alembic nunca los detecta ni los
    compara -- viven solo aquí y en `edw/07` (referencia histórica).

Nota: esta revisión NO reproduce los `COMMENT ON TABLE/COLUMN` de `edw/07` a propósito
-- son el otro tipo de objeto que generaría ruido de comparación permanente
(`modify_comment` en cada diff, incluso sin cambios reales) sin que
`alembic revision --autogenerate` los gestione de forma nativa. La documentación de
cada tabla vive en los docstrings de los modelos SQLAlchemy y en `edw/07` (referencia).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0001_baseline_public'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'comision_config_vendedor',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('id_vendedor_origen', sa.String(length=15), nullable=False),
        sa.Column('tipo', sa.String(length=10), nullable=False),
        sa.Column('factor_tipo', sa.Numeric(precision=4, scale=2), nullable=False),
        sa.Column('fecha_ingreso', sa.Date(), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=False),
        sa.Column('vigente_desde', sa.Date(), nullable=False),
        sa.Column('vigente_hasta', sa.Date(), nullable=True),
        sa.CheckConstraint("tipo IN ('externo','interno')", name='check_tipo_vendedor_valido'),
        sa.CheckConstraint('factor_tipo >= 0 AND factor_tipo <= 1.5', name='check_factor_tipo_valido'),
        sa.PrimaryKeyConstraint('id'),
        schema='public',
    )
    op.create_index(op.f('ix_public_comision_config_vendedor_id'), 'comision_config_vendedor', ['id'], unique=False, schema='public')
    op.create_index('uq_comision_config_vendedor_vigente', 'comision_config_vendedor', ['id_vendedor_origen'], unique=True, schema='public', postgresql_where=sa.text('vigente_hasta IS NULL'))

    op.create_table(
        'comision_factores_credito',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('dias_desde', sa.Integer(), nullable=False),
        sa.Column('dias_hasta', sa.Integer(), nullable=True),
        sa.Column('factor', sa.Numeric(precision=4, scale=2), nullable=False),
        sa.Column('pct_al_facturar', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('vigente_desde', sa.Date(), nullable=False),
        sa.Column('vigente_hasta', sa.Date(), nullable=True),
        sa.CheckConstraint('dias_desde >= 0', name='check_dias_desde_valido'),
        sa.CheckConstraint('factor >= 0 AND factor <= 1.5', name='check_factor_credito_valido'),
        sa.PrimaryKeyConstraint('id'),
        schema='public',
    )
    op.create_index(op.f('ix_public_comision_factores_credito_id'), 'comision_factores_credito', ['id'], unique=False, schema='public')

    op.create_table(
        'comision_liquidaciones',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('anio', sa.Integer(), nullable=False),
        sa.Column('mes', sa.Integer(), nullable=False),
        sa.Column('id_vendedor_origen', sa.String(length=15), nullable=False),
        sa.Column('esquema', sa.String(length=10), nullable=False),
        sa.Column('modo', sa.String(length=10), nullable=False),
        sa.Column('comision_total', sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column('detalle_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('fecha_calculo', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("esquema IN ('plana','variable')", name='check_esquema_valido'),
        sa.CheckConstraint("modo IN ('sombra','oficial')", name='check_modo_liquidacion_valido'),
        sa.CheckConstraint('mes BETWEEN 1 AND 12', name='check_mes_liquidacion_valido'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('anio', 'mes', 'id_vendedor_origen', 'esquema', 'modo', name='uq_comision_liquidacion'),
        schema='public',
    )
    op.create_index(op.f('ix_public_comision_liquidaciones_id'), 'comision_liquidaciones', ['id'], unique=False, schema='public')

    op.create_table(
        'intentos_login_fallidos',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('email', sa.String(length=100), nullable=False),
        sa.Column('ip', sa.String(length=45), nullable=True),
        sa.Column('fecha', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        schema='public',
    )
    op.create_index(op.f('ix_public_intentos_login_fallidos_email'), 'intentos_login_fallidos', ['email'], unique=False, schema='public')
    op.create_index(op.f('ix_public_intentos_login_fallidos_fecha'), 'intentos_login_fallidos', ['fecha'], unique=False, schema='public')
    op.create_index(op.f('ix_public_intentos_login_fallidos_id'), 'intentos_login_fallidos', ['id'], unique=False, schema='public')

    op.create_table(
        'roles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=50), nullable=False),
        sa.Column('descripcion', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        schema='public',
    )
    op.create_index(op.f('ix_public_roles_id'), 'roles', ['id'], unique=False, schema='public')
    op.create_index(op.f('ix_public_roles_nombre'), 'roles', ['nombre'], unique=True, schema='public')

    op.create_table(
        'usuarios',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=100), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('rol_id', sa.Integer(), nullable=False),
        sa.Column('sucursal', sa.String(length=50), nullable=True),
        sa.Column('id_vendedor_origen', sa.String(length=15), nullable=True),
        sa.Column('codalm', sa.String(length=10), nullable=True),
        sa.Column('es_activo', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['rol_id'], ['public.roles.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id_vendedor_origen'),
        schema='public',
    )
    op.create_index(op.f('ix_public_usuarios_email'), 'usuarios', ['email'], unique=True, schema='public')
    op.create_index(op.f('ix_public_usuarios_id'), 'usuarios', ['id'], unique=False, schema='public')

    op.create_table(
        'anomalias_revisiones',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('transaccion_id', sa.String(length=50), nullable=False),
        sa.Column('score', sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column('estado', sa.String(length=20), nullable=False),
        sa.Column('revisor_id', sa.Integer(), nullable=True),
        sa.Column('nota', sa.Text(), nullable=True),
        sa.Column('fecha_deteccion', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('fecha_revision', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("estado IN ('nueva', 'revisada', 'descartada', 'confirmada')", name='check_estado_revision_valido'),
        sa.ForeignKeyConstraint(['revisor_id'], ['public.usuarios.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        schema='public',
    )
    op.create_index(op.f('ix_public_anomalias_revisiones_estado'), 'anomalias_revisiones', ['estado'], unique=False, schema='public')
    op.create_index(op.f('ix_public_anomalias_revisiones_id'), 'anomalias_revisiones', ['id'], unique=False, schema='public')
    op.create_index(op.f('ix_public_anomalias_revisiones_transaccion_id'), 'anomalias_revisiones', ['transaccion_id'], unique=True, schema='public')

    op.create_table(
        'comision_matriz_categorias',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('clase', sa.String(length=5), nullable=False),
        sa.Column('subclase', sa.String(length=5), nullable=True),
        sa.Column('grupo', sa.String(length=1), nullable=False),
        sa.Column('tasa_pct', sa.Numeric(precision=6, scale=3), nullable=False),
        sa.Column('base', sa.String(length=10), nullable=False),
        sa.Column('factor_estrategico', sa.Numeric(precision=4, scale=2), nullable=False),
        sa.Column('vigente_desde', sa.Date(), nullable=False),
        sa.Column('vigente_hasta', sa.Date(), nullable=True),
        sa.Column('creado_por', sa.Integer(), nullable=True),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("base IN ('margen','valor')", name='check_base_valida'),
        sa.CheckConstraint("grupo IN ('A','B','C','S','X')", name='check_grupo_valido'),
        sa.CheckConstraint('factor_estrategico >= 0.5 AND factor_estrategico <= 1.5', name='check_factor_estrategico_valido'),
        sa.CheckConstraint('tasa_pct >= 0 AND tasa_pct <= 100', name='check_tasa_pct_valida'),
        sa.ForeignKeyConstraint(['creado_por'], ['public.usuarios.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        schema='public',
    )
    op.create_index(op.f('ix_public_comision_matriz_categorias_id'), 'comision_matriz_categorias', ['id'], unique=False, schema='public')

    op.create_table(
        'gestion_cartera_eventos',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('fecha', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('cliente_sk', sa.Integer(), nullable=True),
        sa.Column('evento', sa.String(length=20), nullable=False),
        sa.Column('motivo', sa.Text(), nullable=True),
        sa.CheckConstraint("evento IN ('contactado', 'recompro', 'perdido')", name='check_gestion_evento_valido'),
        sa.ForeignKeyConstraint(['usuario_id'], ['public.usuarios.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        schema='public',
    )
    op.create_index(op.f('ix_public_gestion_cartera_eventos_id'), 'gestion_cartera_eventos', ['id'], unique=False, schema='public')

    op.create_table(
        'metas_comerciales_operativas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('anio', sa.Integer(), nullable=False),
        sa.Column('mes', sa.Integer(), nullable=False),
        sa.Column('id_vendedor_origen', sa.String(length=15), nullable=True),
        sa.Column('monto_meta', sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column('unidades_meta', sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column('comision_base_pct', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('bono_sobrecumplimiento', sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column('estado', sa.String(length=20), nullable=False),
        sa.Column('approved_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("estado IN ('PROPUESTA', 'APROBADA', 'RECHAZADA')", name='check_estado_valido'),
        sa.CheckConstraint('anio >= 2020', name='check_anio_valido'),
        sa.CheckConstraint('bono_sobrecumplimiento >= 0', name='check_bono_sobre_valido'),
        sa.CheckConstraint('comision_base_pct BETWEEN 0 AND 100', name='check_comision_base_pct_valida'),
        sa.CheckConstraint('mes BETWEEN 1 AND 12', name='check_mes_valido'),
        sa.CheckConstraint('monto_meta >= 0', name='check_monto_meta_valido'),
        sa.CheckConstraint('unidades_meta >= 0', name='check_unidades_meta_valido'),
        sa.ForeignKeyConstraint(['approved_by'], ['public.usuarios.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        schema='public',
    )
    op.create_index(op.f('ix_public_metas_comerciales_operativas_id'), 'metas_comerciales_operativas', ['id'], unique=False, schema='public')

    op.create_table(
        'notificaciones',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('tipo_evento', sa.String(length=50), nullable=False),
        sa.Column('rol_destino', sa.String(length=20), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('titulo', sa.String(length=200), nullable=False),
        sa.Column('mensaje', sa.Text(), nullable=False),
        sa.Column('accion_url', sa.String(length=300), nullable=True),
        sa.Column('prioridad', sa.String(length=10), nullable=False),
        sa.Column('contexto', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('leida_por', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('fecha_expira', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("prioridad IN ('alta', 'media', 'baja')", name='check_prioridad_valida'),
        sa.ForeignKeyConstraint(['rol_destino'], ['public.roles.nombre'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['usuario_id'], ['public.usuarios.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        schema='public',
    )
    op.create_index(op.f('ix_public_notificaciones_fecha_creacion'), 'notificaciones', ['fecha_creacion'], unique=False, schema='public')
    op.create_index(op.f('ix_public_notificaciones_id'), 'notificaciones', ['id'], unique=False, schema='public')
    op.create_index(op.f('ix_public_notificaciones_rol_destino'), 'notificaciones', ['rol_destino'], unique=False, schema='public')
    op.create_index(op.f('ix_public_notificaciones_tipo_evento'), 'notificaciones', ['tipo_evento'], unique=False, schema='public')

    op.create_table(
        'recomendaciones_eventos',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('fecha', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('cliente_sk', sa.Integer(), nullable=True),
        sa.Column('producto_origen_cod', sa.String(length=20), nullable=False),
        sa.Column('producto_sugerido_cod', sa.String(length=20), nullable=False),
        sa.Column('score_lift', sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column('motivo', sa.Text(), nullable=True),
        sa.Column('evento', sa.String(length=20), nullable=False),
        sa.Column('fecha_carga', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.CheckConstraint("evento IN ('mostrada', 'aceptada', 'rechazada')", name='check_evento_valido'),
        sa.ForeignKeyConstraint(['usuario_id'], ['public.usuarios.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        schema='public',
    )
    op.create_index(op.f('ix_public_recomendaciones_eventos_id'), 'recomendaciones_eventos', ['id'], unique=False, schema='public')

    # ── public.cliente_lookup (sin modelo SQLAlchemy, ver docstring del módulo) ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS public.cliente_lookup (
            hash_anonimo VARCHAR(64) PRIMARY KEY,
            id_cliente_transaccional VARCHAR(50) NOT NULL,
            nombre_cliente VARCHAR(200),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)

    # ── Trigger updated_at de public.usuarios (único trigger de BD del esquema;
    # el resto de tablas con updated_at, p.ej. metas_comerciales_operativas, lo
    # resuelven a nivel de aplicación vía SQLAlchemy onupdate) ──────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION public.set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("DROP TRIGGER IF EXISTS trg_usuarios_updated_at ON public.usuarios")
    op.execute("""
        CREATE TRIGGER trg_usuarios_updated_at
            BEFORE UPDATE ON public.usuarios
            FOR EACH ROW EXECUTE FUNCTION public.set_updated_at()
    """)


def downgrade() -> None:
    # Downgrade deliberadamente no soportado: esta es la base de la aplicación,
    # no se destruye. Un rollback real de producción vuelve a un backup, no a un
    # esquema vacío.
    raise NotImplementedError(
        "La migración baseline no soporta downgrade: es la base de datos de la "
        "aplicación en producción, no un esquema descartable. Restaurar desde backup "
        "si se necesita revertir."
    )
