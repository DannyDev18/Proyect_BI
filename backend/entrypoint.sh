#!/bin/sh
# backend/entrypoint.sh
# Aplica las migraciones Alembic del esquema `public` antes de levantar uvicorn
# (docs/features/plan_migraciones_esquema_public.md, Fase 2). `set -e`: si la
# migración falla, el contenedor nunca llega a `exec "$@"` -- el backend no arranca
# con un esquema desactualizado.
set -e

# Fase 3 (docs/features/plan_mejora_pipeline_ml.md §5.2.1 opción 1): si el socket de
# Docker del host está montado, este contenedor arranca como root (ver Dockerfile) solo
# para poder ajustar sus permisos -- el GID de su grupo dueño no es predecible (varía
# entre un `docker` group real en Linux y root:root en algunos backends de Docker
# Desktop, confirmado en este entorno de desarrollo). `chmod 666` es deliberadamente
# amplio (no se intenta adivinar/crear el grupo correcto) porque el socket solo es
# accesible DENTRO de este contenedor -- ningún otro proceso del host lo ve a través de
# este bind mount. Si el socket no está montado (instalaciones sin la Fase 3
# habilitada), este paso simplemente no aplica.
if [ -S /var/run/docker.sock ]; then
    chmod 666 /var/run/docker.sock 2>/dev/null || true
fi

# A partir de aquí, todo corre como `appuser` (nunca root) vía gosu.
exec gosu appuser sh -c '
set -e
python scripts/apply_migrations.py
exec "$@"
' -- "$@"
