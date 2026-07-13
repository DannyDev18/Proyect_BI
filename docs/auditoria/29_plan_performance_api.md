# 29 — Plan de pruebas de rendimiento y optimización de la API (sin romper lo existente)

> **Fecha:** 2026-07-13
> **Alcance:** backend FastAPI (`backend/`), consultas al EDW (PostgreSQL 16), percepción de velocidad en el frontend. NO toca el ERP SAP (solo lectura, fuera de alcance), NO cambia contratos de la API.
> **Método:** medición primero (línea base reproducible), optimización después, validación de regresión al final. Ningún cambio se aplica sin su medición "antes".

## 0. Diagnóstico inicial (estado actual verificado en código)

| Hallazgo | Evidencia | Severidad |
|---|---|---|
| Backend 100% síncrono: engine psycopg2, endpoints `def` | `backend/app/database/session.py`, `backend/app/api/routes/*` (0 endpoints `async def`) | Informativo — los endpoints `def` corren en el threadpool de FastAPI (~40 hilos), NO bloquean el event loop. |
| Pool de conexiones hardcodeado y pequeño: `pool_size=5, max_overflow=10` (máx. 15) | `session.py:12-13` | **Alta** — con >15 requests concurrentes con BD activa, los hilos esperan conexión. Es el cuello de botella real de concurrencia. |
| Uvicorn con 1 solo worker (1 proceso) | `backend/Dockerfile:26` | **Media** — la inferencia ML (forecast walk-forward) es CPU-bound y compite por el GIL con el resto de requests. |
| Caché TTL en memoria solo para `prediccion-compras-mes` | `config.py` (`BODEGA_FORECAST_CACHE_TTL_MIN`) | Media — patrón bueno, no extendido a otros KPIs costosos. El EDW se carga por lotes (no intra-hora), así que el TTL es seguro. |
| Sin métricas de tiempo por endpoint ni `pg_stat_statements` | no existe middleware de timing | Media — hoy no se puede saber qué endpoint/consulta es lento sin instrumentar. |

**Riesgo clave a evitar:** convertir endpoints a `async def` dejando dentro llamadas síncronas (SQLAlchemy sync, joblib/sklearn) SÍ bloquearía el event loop y EMPEORARÍA el rendimiento. La migración async debe ser en cadena completa (route → service → repository → engine async) o no hacerse.

## Fase 1 — Línea base de medición (sin tocar código de negocio)

1. **Instrumentación mínima:**
   - Middleware de timing en `main.py` que agregue header `X-Process-Time` y loguee `método, ruta, status, ms` (cambio aditivo, cero riesgo).
   - Habilitar `pg_stat_statements` en `postgres_edw` (parámetro de Docker Compose + `CREATE EXTENSION`) para ranking de consultas por tiempo total.
2. **Suite de carga con Locust** (`backend/tests/perf/locustfile.py`, mismo stack Python):
   - Usuarios simulados por rol (login JWT real): gerencia (KPIs `/analytics`), bodega (`/analytics/bodega/inventario-matriz`, `/salidas-forecast`, `/prediccion-compras-mes`, `/stock-reorden`), ventas (`/analytics/ventas/cross-selling/sugerencias`, `/kpis`).
   - Matriz: 1, 10, 25 y 50 usuarios concurrentes × 3 min cada escalón.
3. **Métricas a capturar (criterio de comparación):** p50 / p95 / p99 por endpoint, RPS, tasa de error, uso del pool (`engine.pool.status()`).
4. **`EXPLAIN (ANALYZE, BUFFERS)`** de las 10 consultas top de `pg_stat_statements`; verificar que los índices de `edw/04_indices.sql` estén realmente aplicados en la BD viva (los DDL solo corren en volumen nuevo — aplicar manualmente los que falten).
5. **Entregable:** tabla "antes" en este mismo reporte. Ninguna optimización se acepta sin comparar contra esto.

## Fase 2 — Quick wins de bajo riesgo (sin cambiar contratos ni arquitectura)

1. **Pool configurable por entorno** (elimina el hardcode, regla de CLAUDE.md):
   ```python
   engine = create_engine(
       settings.SQLALCHEMY_DATABASE_URI,
       pool_pre_ping=True,
       pool_size=settings.DB_POOL_SIZE,        # default 10
       max_overflow=settings.DB_MAX_OVERFLOW,  # default 20
       pool_recycle=1800,
   )
   ```
   Subir también el threadpool de FastAPI si el pool crece (variable `anyio` / `RunVarsThreadLimiter`). Verificar `max_connections` de PostgreSQL (default 100) contra `workers × (pool+overflow)`.
2. **Múltiples workers de Uvicorn en producción:** `--workers 2..4` (CMD del Dockerfile parametrizado por env `UVICORN_WORKERS`, default 1 para no cambiar dev). Cada worker carga sus propios `.pkl` (~memoria ×N, verificar). Esto aísla la inferencia CPU-bound del resto de requests sin tocar una línea de lógica.
3. **Índices faltantes** detectados en Fase 1 → agregar a `edw/04_indices.sql` + aplicar manualmente en la BD existente (documentar en `03_cambios_aplicados.md`).
4. **Extender el patrón de caché TTL** (ya probado en `prediccion-compras-mes`) a los KPIs costosos identificados en Fase 1 (candidatos: rotación-matriz, top-combinaciones de cross-selling, KPIs gerenciales agregados). TTL configurable por env, clave por parámetros (sucursal, fechas). Seguro porque el EDW se carga por lotes.
5. **Reescritura puntual de consultas** solo de las que la Fase 1 marque lentas (CTEs que materializan de más, agregaciones sin índice de apoyo, filtros no sargables), cada una con su EXPLAIN antes/después y verificando resultados idénticos (mismo JSON de respuesta).

## Fase 3 — Concurrencia async (gradual, solo si la Fase 2 no alcanza el objetivo)

Migración **por vertical completa**, no global, empezando por los endpoints de solo lectura más pesados:

1. Motor async paralelo en `session.py`: `create_async_engine` con `asyncpg` (`postgresql+asyncpg://...`) + `async_sessionmaker`, **coexistiendo** con el engine sync actual. Nada de lo existente se toca.
2. Dependencia nueva `AsyncSessionDep` en `core/deps.py` junto a la actual.
3. Migrar UNA vertical piloto (sugerido: `warehouse`: route → `WarehouseService` → `WarehouseRepository` a `async def` + `await session.execute(...)`). Las consultas son `text()` crudo en su mayoría, así que el cambio es mecánico.
4. La inferencia ML dentro de verticales async va a threadpool: `await anyio.to_thread.run_sync(model.predict, X)` — nunca llamada directa dentro de `async def`.
5. Medir la vertical piloto con Locust vs. su versión sync. Solo si mejora p95 bajo 25-50 usuarios se migran las demás verticales (analytics, sales); auth/users/roles pueden quedar sync para siempre.
6. Al final, si TODO migró: retirar el engine sync. Si no, ambos conviven sin conflicto (pools separados — dimensionarlos en conjunto).

**Regla de oro:** prohibido `async def` en un endpoint cuyo interior siga siendo sync-bloqueante.

## Fase 4 — Percepción de velocidad en el frontend (complementario)

- Ajustar `staleTime`/`gcTime` de TanStack Query por dominio (los datos del EDW cambian por lotes → `staleTime` de minutos es seguro; hoy los defaults refetchean de más).
- `placeholderData: keepPreviousData` en las tablas paginadas de Bodega (evita el "flash" de loading al cambiar de página).
- `prefetchQuery` de la página siguiente en la paginación y de los KPIs del dashboard destino al hacer hover en el Sidebar.
- Verificar que ninguna página dispare consultas en cascada secuencial pudiendo ser paralelas.

## Fase 5 — Validación y cierre

1. Repetir la matriz Locust completa (misma semilla de escenarios) → tabla "después" junto a la de "antes".
2. **Criterio de aceptación sugerido:** p95 < 1.5 s en todos los endpoints de dashboard con 25 usuarios concurrentes; ninguna regresión funcional.
3. `pytest` completo (`backend/tests/unit` + `integration`) en verde; los schemas Pydantic de respuesta no cambian (contrato API intacto → frontend intacto).
4. Actualizar este reporte con resultados, y `02_reglas_negocio_validadas.md` si surge alguna regla nueva (p. ej. TTLs de caché como parámetros de negocio).

## Guardrails (aplican a todas las fases)

- SAP Producción: intocable (ni siquiera participa — todo es contra el EDW).
- Cero cambios de contrato API (mismos paths, mismos schemas de request/response).
- Todo parámetro nuevo va por variable de entorno con default igual al comportamiento actual (rollback = no definir la variable).
- Cada fase se mide contra la línea base antes de pasar a la siguiente; si una optimización no mueve el p95, se revierte.

## Orden de ejecución y esfuerzo estimado

| Fase | Riesgo | Esfuerzo | Impacto esperado |
|---|---|---|---|
| 1. Línea base | Nulo | 1 día | Visibilidad total |
| 2. Quick wins | Bajo | 1-2 días | Alto (pool + workers + caché suelen resolver el 80%) |
| 3. Async gradual | Medio | 2-4 días | Alto solo bajo alta concurrencia real |
| 4. Frontend | Bajo | 0.5-1 día | Alto en percepción del usuario |
| 5. Validación | Nulo | 0.5 día | Evidencia para la tesis |
