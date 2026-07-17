#!/bin/sh
# backend/entrypoint.sh
# Aplica las migraciones Alembic del esquema `public` antes de levantar uvicorn
# (docs/features/plan_migraciones_esquema_public.md, Fase 2). `set -e`: si la
# migración falla, el contenedor nunca llega a `exec "$@"` -- el backend no arranca
# con un esquema desactualizado.
set -e

python scripts/apply_migrations.py

exec "$@"
