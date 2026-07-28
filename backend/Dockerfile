FROM python:3.11-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev gcc curl ca-certificates gosu \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian bookworm stable" \
        > /etc/apt/sources.list.d/docker.list \
    && apt-get update && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# `appuser`: identidad no-root para el proceso de la app (uvicorn) en producción.
# Fase 3 (docs/features/plan_mejora_pipeline_ml.md §5.2.1 opción 1): el backend
# dispara el reentrenamiento con `docker compose run --rm ml ...` en el HOST vía el
# socket de Docker montado en docker-compose.yml -- NUNCA instalando el código de
# entrenamiento dentro de esta imagen (arquitectura backend↔ml separadas, CLAUDE.md).
# El contenedor arranca como root (sin `USER` aquí) a propósito: `entrypoint.sh` ajusta
# los permisos del socket montado en tiempo de ejecución (el GID de su grupo dueño
# varía entre Linux con `docker` group y Docker Desktop, que en algunos backends lo
# expone como root:root -- verificado en este entorno) y luego usa `gosu` para bajar
# el proceso real de la app a `appuser`, nunca corre uvicorn como root. Riesgo de
# seguridad documentado: cualquier proceso con acceso al socket de Docker tiene control
# equivalente a root sobre el host (§11 del plan) -- decisión de infraestructura
# confirmada explícitamente, no un descuido.
RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/ml_models \
    && chown -R appuser:appuser /app \
    && chmod +x entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# entrypoint.sh aplica las migraciones Alembic del esquema public (docs/features/
# plan_migraciones_esquema_public.md) y luego hace `exec "$@"` con el CMD de abajo --
# tanto aquí como en docker-compose.override.yml (que sobreescribe el CMD con
# --reload para desarrollo, pero no el ENTRYPOINT).
ENTRYPOINT ["./entrypoint.sh"]

# Sin --reload: eso es solo para desarrollo (ver docker-compose.override.yml, que
# sobreescribe este CMD con --reload cuando corre `docker compose up` localmente).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
