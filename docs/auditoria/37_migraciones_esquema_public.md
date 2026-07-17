# Auditoría 37 — Migraciones versionadas del esquema `public` (Alembic)

> **Fecha:** 2026-07-16
> **Alcance:** `docs/features/plan_migraciones_esquema_public.md` — adopción de Alembic como único dueño del esquema `public`, para que un contenedor Docker nuevo (dev o producción) cree/actualice el esquema automáticamente al arrancar, sin pasos manuales de DDL.
> **Método:** comparación estática DDL vs modelos + validación dinámica contra Postgres real (contenedor de desarrollo `bi_postgres_edw` en `localhost:5433`, y contenedores Postgres 16-alpine desechables levantados para este ejercicio).

## 1. Hallazgos de la Fase 0 (comparación DDL vs modelos vs BD real)

### H-1 (crítico, corregido): copiar el DDL de `edw/07` tal cual genera ruido permanente en `--autogenerate`

Primer intento de la migración baseline: copiar literalmente el SQL de `edw/07_public_app_tables.sql` en `op.execute()`. Se validó con `alembic.autogenerate.compare_metadata` contra una BD recién creada con esa baseline: **53 diferencias**, todas cosméticas pero permanentes — `edw/07` usa `UNIQUE`/índices sin nombre (`email VARCHAR(100) UNIQUE`) mientras los modelos SQLAlchemy declaran `unique=True, index=True` (constraint nombrado `ix_public_usuarios_email`). Cada futuro `alembic revision --autogenerate` habría arrastrado este ruido para siempre, aunque no hubiera ningún cambio real de modelo.

**Corrección:** la migración baseline (`0001_baseline_public`) no copia el SQL de `edw/07` — usa DDL congelado generado una sola vez comparando `Base.metadata` contra un Postgres vacío (`alembic revision --autogenerate` desde cero), pegado a mano en el archivo de migración. Verificado: **0 diferencias** (salvo H-2) al comparar `Base.metadata` contra una BD recién migrada a `head`.

### H-2 (aceptado, documentado): FK con schema explícito vs reflejado sin schema

Incluso con DDL congelado y alineado, `compare_metadata` sigue mostrando 16 diffs (`add_fk`/`remove_fk`, uno por cada FK entre tablas de `public`). Causa: Postgres refleja una FK hacia una tabla del **mismo esquema** sin el prefijo `public.`, mientras los modelos la declaran explícita (`ForeignKey("public.usuarios.id")`). Es la misma constraint, solo difiere la forma en que Alembic la compara.

Se intentó corregir quitando el prefijo `public.` en los 8 `ForeignKey(...)` de los modelos (`anomalia_revision.py`, `commission_config.py`, `gestion_cartera_evento.py`, `goal.py`, `notification.py`, `recommendation_event.py`, `user.py`) — **rompió la creación de tablas**: `NoReferencedTableError` al ejecutar `Base.metadata.create_all`, porque SQLAlchemy no infiere el schema de la tabla referenciada a partir del schema de la tabla que declara la FK (solo lo hace vía `MetaData(schema=...)` a nivel global, que este proyecto no usa). Los 8 archivos se revirtieron a su estado original (`ForeignKey("public.usuarios.id", ...)`).

**Decisión:** aceptar este ruido como conocido y permanente. El test de guardia (`tests/integration/test_alembic_schema_sync.py`) lo filtra explícitamente (`_es_diff_fk_schema_cosmetica`) y documenta la causa en su docstring y en `alembic/env.py`.

### H-3 (bug de diseño, corregido antes de aplicarse en ningún ambiente): baseline delegando en `Base.metadata.create_all` en tiempo de ejecución

Segundo intento de la baseline: en vez de DDL congelado, `upgrade()` llamaba a `Base.metadata.create_all(bind=op.get_bind())`, usando la metadata **viva** de los modelos. Al agregar una columna de prueba a `Role` y volver a migrar una BD ya sellada en `head`, la columna nunca llegó (0001 ya había corrido, no se re-ejecuta) — pero en una BD **nueva**, la misma columna aparecía automáticamente sin ninguna migración nueva. Esto rompe la garantía central de Alembic (mismo `upgrade head` ⇒ mismo esquema, sin importar el punto de partida) y habría dejado pasar en silencio cualquier cambio de modelo sin migración.

**Corrección:** DDL 100% congelado (ver H-1), nunca dependiente de la metadata en tiempo de ejecución. Confirmado con un test negativo: agregar una columna sin migración hace *fallar* `test_alembic_schema_sync.py` (antes de la corrección, el mismo test pasaba erróneamente).

### H-4: `public.cliente_lookup` no tiene modelo SQLAlchemy

El ETL escribe ahí con SQL crudo (`catalog_repository.py`, `cartera360_repository.py`, `prediction_repository.py`); el backend nunca la mapea. Sin excluirla explícitamente, cualquier `--autogenerate` la vería "huérfana" (no está en `Base.metadata`) y propondría un `DROP TABLE`. `alembic/env.py::include_object` la excluye por nombre. La migración baseline la crea con SQL crudo, igual que `edw/07`.

### H-5: `edw/09_vistas_ml.sql` depende de `public.cliente_lookup` en el mismo `initdb`

`ml.v_ventas_cruzadas_desanonima` hace `JOIN public.cliente_lookup`. Esto **impide** retirar `edw/07`/`edw/08` del `docker-entrypoint-initdb.d` (opción "a" del plan, "Alembic crea todo desde cero"): Alembic solo corre cuando arranca el contenedor del backend, **después** de que Postgres ya completó su secuencia de `initdb` — si `cliente_lookup` no existiera todavía, la vista de `edw/09` fallaría al crear un volumen nuevo.

**Decisión (opción "b" del plan):** `edw/07`/`edw/08` se conservan activos en `docker-entrypoint-initdb.d`, con cabecera "REFERENCIA" agregada indicando que la fuente de verdad de cambios de *esquema* es `backend/alembic/`. El backend detecta al arrancar si la BD fue inicializada así (existe `public.usuarios`, no existe `public.alembic_version`) y la sella con `alembic stamp 0001_baseline_public` antes de aplicar lo pendiente.

### H-6: no hay drift entre `edw/07`/modelos SQLAlchemy en las 13 tablas de `public`

Comparación tabla por tabla (13 tablas: 12 modeladas + `cliente_lookup`) entre el DDL de `edw/07`, los modelos SQLAlchemy y el esquema real de la BD de desarrollo (`localhost:5433`): mismas columnas, tipos, nullability y constraints de negocio (CHECKs). Las únicas diferencias son las de nomenclatura de índices/constraints ya cubiertas en H-1/H-2, no de estructura.

## 2. Validación dinámica (contenedores Postgres 16-alpine desechables)

| Escenario | Comando | Resultado |
|---|---|---|
| Volumen vacío → `alembic upgrade head` | `alembic upgrade head` sobre Postgres recién creado | Crea las 13 tablas + trigger + seed de roles/admin. Verificado con `\dt` y `SELECT` sobre `public.roles`/`public.usuarios`. |
| BD recién migrada vs `Base.metadata` | `compare_metadata` tras `upgrade head` | 0 diffs, salvo el ruido de FK documentado en H-2. |
| Cambio de modelo sin migración (negativo) | agregar columna a `Role`, re-ejecutar el test de guardia | Falla correctamente (antes de H-3, pasaba erróneamente). |
| **Adopción de una BD pre-Alembic real** (volumen inicializado con `edw/01..09` completo, igual que producción) | `python scripts/apply_migrations.py` | Detecta `usuarios` sin `alembic_version`, ejecuta `alembic stamp 0001_baseline_public` (no re-ejecuta DDL) y luego `alembic upgrade head` (aplica `0002_seed_roles`, no-op sobre los 4 usuarios ya sembrados por `edw/08`, `ON CONFLICT DO NOTHING`). Verificado: `alembic_version = 0002_seed_roles`, los 4 usuarios semilla intactos con su hash original. |

No se probó contra la BD compartida de desarrollo (`localhost:5433`, usada por el resto de la suite de integración) para no mutar su estado como parte de esta auditoría — la validación de "adopción" se hizo contra una réplica desechable inicializada de forma idéntica (mismos `edw/01..09`).

## 3. Cambios aplicados

- **`backend/alembic/`** (nuevo): `env.py` (URL desde `app.core.config.settings`, filtro `include_object` que excluye `edw.*`/`ml.*` y `cliente_lookup`, `version_table_schema="public"`), `versions/0001_baseline_public.py` (DDL congelado de las 12 tablas modeladas + `cliente_lookup` + trigger `set_updated_at`, `downgrade()` no soportado a propósito), `versions/0002_seed_roles.py` (seed idempotente de los 4 roles + admin inicial, contraseña desde `ADMIN_INITIAL_PASSWORD`, **sin** el hash bcrypt fijo de `edw/08`).
- **`backend/requirements.txt`:** agrega `alembic`.
- **`backend/scripts/apply_migrations.py`** (nuevo): detecta BD pre-Alembic (`usuarios` sin `alembic_version`) y la sella antes de aplicar `upgrade head`.
- **`backend/entrypoint.sh`** (nuevo) + **`backend/Dockerfile`**: `ENTRYPOINT` que corre las migraciones antes de `exec "$@"` (el `CMD` de uvicorn); si las migraciones fallan, el contenedor nunca arranca con esquema desactualizado.
- **`backend/app/main.py`:** retirado `Base.metadata.create_all` y el `ALTER TABLE ... codalm` hardcodeado del lifespan (D-2/D-3 del plan, resueltos) — el esquema `public` ya no se toca desde el proceso del backend, solo desde el entrypoint antes de que uvicorn levante.
- **`backend/tests/integration/test_alembic_schema_sync.py`** (nuevo): test de guardia — falla si un modelo cambia sin migración correspondiente, usando una BD desechable vía `ALEMBIC_TEST_DATABASE_URL` (no la BD compartida de desarrollo, que conserva nomenclatura heredada de `edw/07` y jamás calzaría 1:1, ver H-1).
- **`edw/07_public_app_tables.sql` / `edw/08_seed_roles_usuarios.sql`:** cabecera "REFERENCIA" — se conservan funcionalmente activos en `initdb` (H-5) pero dejan de ser la fuente de verdad de cambios de esquema.
- **`.env.example` / `.env`:** nueva variable `ADMIN_INITIAL_PASSWORD`.

## 4. Pendiente resuelto en el seguimiento de esta sesión

- **`docs/deploy/instalacion_windows_server_paso_a_paso.md`:** agregado `§6.1 Levantar el backend` documentando `docker compose up -d backend` y la aplicación automática de migraciones (incluye verificación de `alembic_version` y del admin sembrado); `ADMIN_INITIAL_PASSWORD` agregada a la lista de valores obligatorios de `.env` en `§5`.
- **Flujo contra la BD compartida de desarrollo (`localhost:5433`):** ejecutado como parte del seguimiento — se reconstruyó y reinició el contenedor real `bi_backend`; detectó la BD pre-Alembic, la selló (`0001_baseline_public`) y aplicó `0002_seed_roles`. Verificado sin pérdida de datos (`cliente_lookup` 73 368 filas, `metas_comerciales_operativas` 18 filas, los 16 usuarios existentes intactos) y con `/health` + login de `admin@empresa.com` respondiendo correctamente tras el reinicio.
  - Detalle no bloqueante detectado durante esa ejecución: la primera vez que se corrió `scripts/apply_migrations.py` dentro del contenedor falló con `ModuleNotFoundError: No module named 'app'` — al invocarse como `python scripts/apply_migrations.py`, Python solo agrega el directorio del script (`scripts/`) a `sys.path`, no `/app`. Corregido insertando `_BACKEND_DIR` en `sys.path` al inicio del script.

## 5. Pendiente real (fuera de alcance de este proyecto, sin pipeline que lo requiera)

- Test de guardia (`compare_metadata`) sobre `ALEMBIC_TEST_DATABASE_URL`: requiere una BD desechable en CI. El repositorio no tiene ningún pipeline de CI configurado todavía (no existe `.github/workflows/` ni equivalente) — no hay nada que provisionar por ahora; queda documentado para cuando se agregue CI.
