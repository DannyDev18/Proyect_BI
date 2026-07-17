# backend/scripts/apply_migrations.py
"""Aplica las migraciones Alembic del esquema `public` al arrancar el contenedor del
backend -- Fase 2 de docs/features/plan_migraciones_esquema_public.md. Se ejecuta
desde `entrypoint.sh` ANTES de levantar uvicorn: si falla, el contenedor nunca arranca
con un esquema desactualizado (falla rápido, en vez de fallar en el primer request).

Tres escenarios posibles, todos manejados por la misma secuencia stamp-si-hace-falta +
upgrade:
  1. BD completamente vacía (volumen Docker nuevo): no hay `public.usuarios` ni
     `public.alembic_version` -- `alembic upgrade head` crea todo desde 0001.
  2. BD pre-Alembic (dev actual, o una producción ya inicializada con
     `edw/07_public_app_tables.sql` vía initdb): existe `public.usuarios` pero no
     `public.alembic_version` -- se sella con `alembic stamp 0001_baseline_public`
     (no re-ejecuta el DDL, ya existe) y luego `alembic upgrade head` aplica solo lo
     que falte desde ahí en adelante (hoy, 0002_seed_roles).
  3. BD ya sellada (`alembic_version` existe): `alembic upgrade head` es no-op si ya
     está al día, o aplica las migraciones pendientes.
"""
import logging
import os
import sys

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

logger = logging.getLogger("Backend.Migrations")
logging.basicConfig(level=logging.INFO, format="%(levelname)-5.5s [%(name)s] %(message)s")

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BASELINE_REVISION = "0001_baseline_public"

# Ejecutado como `python scripts/apply_migrations.py` (entrypoint.sh): Python solo
# agrega el directorio del propio script (scripts/) a sys.path, no /app -- sin esto
# `from app.core.config import settings` falla con ModuleNotFoundError.
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


def _bd_es_pre_alembic(engine: sa.engine.Engine) -> bool:
    inspector = sa.inspect(engine)
    tablas = set(inspector.get_table_names(schema="public"))
    return "usuarios" in tablas and "alembic_version" not in tablas


def main() -> None:
    # Import diferido: app.core.config valida configuración de proceso (JWT_SECRET,
    # etc.) al importarse -- solo se necesita para resolver la URL de conexión aquí.
    from app.core.config import settings

    alembic_cfg = Config(os.path.join(_BACKEND_DIR, "alembic.ini"))
    alembic_cfg.set_main_option("script_location", os.path.join(_BACKEND_DIR, "alembic"))

    engine = sa.create_engine(settings.SQLALCHEMY_DATABASE_URI)
    try:
        if _bd_es_pre_alembic(engine):
            logger.info(
                "BD pre-Alembic detectada (existe public.usuarios, no existe "
                "alembic_version) -- sellando en %s sin re-ejecutar su DDL.",
                _BASELINE_REVISION,
            )
            command.stamp(alembic_cfg, _BASELINE_REVISION)
    finally:
        engine.dispose()

    logger.info("Aplicando migraciones pendientes (alembic upgrade head)...")
    command.upgrade(alembic_cfg, "head")
    logger.info("Esquema public al día.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("Fallo al aplicar migraciones -- el backend NO va a arrancar.")
        sys.exit(1)
