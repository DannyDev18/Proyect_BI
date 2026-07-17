from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Registra los 12 modelos de public.* (app/database/base.py) y expone la URL de
# conexión real del backend -- una sola fuente de verdad con app/core/config.py,
# nunca credenciales duplicadas en alembic.ini (docs/features/plan_migraciones_esquema_public.md).
import app.database.base  # noqa: F401
from app.core.config import settings
from app.database.session import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Solo se usa el DATABASE_URL del backend si el caller (CLI `alembic`, o un Config
# programático como el del test de guardia en
# tests/integration/test_alembic_schema_sync.py) no inyectó ya una URL explícita --
# el placeholder de alembic.ini nunca es un valor real, así que su presencia es la
# señal de "nadie la fijó todavía".
if config.get_main_option("sqlalchemy.url") in (None, "driver://user:pass@localhost/dbname"):
    config.set_main_option("sqlalchemy.url", settings.SQLALCHEMY_DATABASE_URI)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


# Tablas de `public` sin modelo SQLAlchemy -- viven solo en la migración baseline
# (0001_baseline_public) y las escribe SQL crudo del ETL, nunca el backend. Sin este
# filtro, cualquier `--autogenerate` futuro las vería como "huérfanas" (no están en
# Base.metadata) y propondría un DROP TABLE espurio (confirmado con
# alembic.autogenerate.compare_metadata contra la BD de dev, ver auditoría 37).
_TABLAS_SIN_MODELO = {"cliente_lookup"}


def include_object(object, name, type_, reflected, compare_to):
    """Alembic es dueño exclusivo del esquema `public`. Los esquemas `edw.*` y `ml.*`
    son territorio del ETL (edw/01..06 y 09) -- nunca deben aparecer en un
    --autogenerate ni ser candidatos a DROP por "no estar en Base.metadata"."""
    schema = getattr(object, "schema", None)
    if schema not in (None, "public"):
        return False
    if type_ == "table" and name in _TABLAS_SIN_MODELO:
        return False
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        include_object=include_object,
        version_table_schema="public",
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_object=include_object,
            version_table_schema="public",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
