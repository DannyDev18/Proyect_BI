FROM python:3.11-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev gcc curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Usuario no-root para producción.
RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/ml_models \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Sin --reload: eso es solo para desarrollo (ver docker-compose.override.yml, que
# sobreescribe este CMD con --reload cuando corre `docker compose up` localmente).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
