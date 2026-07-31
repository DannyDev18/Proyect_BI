# backend/tests/integration/test_alembic_schema_sync.py
"""Test de guardia (Fase 4 punto 2, docs/features/plan_migraciones_esquema_public.md):
falla si alguien cambia un modelo SQLAlchemy sin generar la migración Alembic
correspondiente -- ataca de raíz el drift D-4 documentado en el plan (dos fuentes de
verdad que antes solo se sincronizaban a mano).

Corre contra una BD DESECHABLE (Postgres vacío, "efímero"), NO contra la BD compartida
de desarrollo (`postgres_edw`, PG_HOST/PG_PORT): esa BD la creó originalmente
`edw/07_public_app_tables.sql` a mano (constraints/índices sin nombre) y jamás va a
calzar 1:1 con `Base.metadata` aunque no haya ningún drift real -- solo migrarla
(`alembic stamp` + `upgrade`) no reescribe objetos ya existentes. Un Postgres recién
creado y llevado a `alembic upgrade head` sí es 100% comparable: la migración baseline
(0001_baseline_public) delega la creación de tabla en el propio `Base.metadata`, así
que ambos deben calzar exactamente salvo un único ruido cosmético documentado abajo.

Requiere `ALEMBIC_TEST_DATABASE_URL` apuntando a un Postgres vacío desechable (p.ej.
`docker run --rm -d -e POSTGRES_PASSWORD=x -e POSTGRES_DB=test -p 5555:5432
postgres:16-alpine`, ver docs/auditoria/37_migraciones_esquema_public.md). Sin esa
variable, se salta -- no se asume ningún Postgres de scratch disponible en CI.
"""
import os

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

import app.database.base  # noqa: F401 -- registra los 12 modelos en Base.metadata
from app.database.session import Base

pytestmark = pytest.mark.integration

_TABLAS_SIN_MODELO = {"cliente_lookup"}
_ALEMBIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "alembic")


def _include_object(object, name, type_, reflected, compare_to):
    schema = getattr(object, "schema", None)
    if schema not in (None, "public"):
        return False
    if type_ == "table" and name in _TABLAS_SIN_MODELO:
        return False
    return True


def _es_diff_fk_schema_cosmetica(diff) -> bool:
    """True si `diff` es un elemento de un par add_fk/remove_fk que difiere solo en
    la cualificación de esquema del lado referenciado -- confirmado con
    `compare_metadata` contra una BD recién migrada (docs/auditoria/37_...md): Postgres
    refleja la FK sin el prefijo `public.` aunque el modelo lo declare explícito
    (`ForeignKey("public.usuarios.id")`), es la misma constraint funcionalmente."""
    return isinstance(diff, tuple) and diff and diff[0] in ("add_fk", "remove_fk")


def test_modelos_sqlalchemy_sincronizados_con_migraciones():
    test_db_url = os.getenv("ALEMBIC_TEST_DATABASE_URL")
    if not test_db_url:
        pytest.skip(
            "ALEMBIC_TEST_DATABASE_URL no está definida -- apunta a un Postgres vacío "
            "desechable para correr este test (ver docstring del módulo)."
        )

    alembic_cfg = Config(os.path.join(_ALEMBIC_DIR, "..", "alembic.ini"))
    alembic_cfg.set_main_option("script_location", _ALEMBIC_DIR)
    alembic_cfg.set_main_option("sqlalchemy.url", test_db_url)
    command.upgrade(alembic_cfg, "head")

    engine = sa.create_engine(test_db_url)
    with engine.connect() as conn:
        mc = MigrationContext.configure(
            conn,
            opts={
                "include_schemas": True,
                "include_object": _include_object,
                "compare_type": True,
            },
        )
        diffs = compare_metadata(mc, Base.metadata)

    diffs_inesperadas = [d for d in diffs if not _es_diff_fk_schema_cosmetica(d)]

    assert not diffs_inesperadas, (
        "Base.metadata (modelos SQLAlchemy) y el esquema public de una BD recién "
        "migrada a head divergen fuera del ruido cosmético conocido de FKs -- falta "
        "generar una migración Alembic (`alembic revision --autogenerate`) para este "
        f"cambio de modelo. Diffs: {diffs_inesperadas}"
    )
