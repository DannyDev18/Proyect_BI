# Plan — Migraciones versionadas del esquema `public` (dev → producción)

> **Fecha:** 2026-07-16
> **Estado:** Propuesta (requiere auditoría previa `docs/auditoria/37_migraciones_esquema_public.md`)
> **Alcance:** `backend/` (nuevo directorio `alembic/`, `app/main.py`, `app/database/base.py`, `requirements.txt`, `Dockerfile`/entrypoint), `edw/07_public_app_tables.sql` y `edw/08_seed_roles_usuarios.sql` (cambio de rol: de fuente de verdad a referencia), `docker-compose.yml`, `docs/deploy/instalacion_windows_server_paso_a_paso.md`.
> **Fuera de alcance:** los esquemas `edw.*` y `ml.*` (territorio del ETL, DDL en `edw/01..06` y `09`) — este plan NO los toca.

## 0. Problema y diagnóstico

**Problema:** al migrar de desarrollo a producción, las tablas del esquema `public` (auth, metas, comisiones, notificaciones, triage, telemetría) no tienen un mecanismo confiable de creación/actualización. Hoy conviven **tres mecanismos que compiten**, y ninguno migra cambios de esquema sobre una BD existente:

| # | Mecanismo | Limitación | Evidencia |
|---|---|---|---|
| D-1 | `edw/07_public_app_tables.sql` + `edw/08_seed_roles_usuarios.sql` vía `/docker-entrypoint-initdb.d` | Solo corre en **volumen Docker nuevo**. Una BD de producción ya inicializada nunca lo re-ejecuta. | `docker-compose.yml`, CLAUDE.md §Restricciones |
| D-2 | `Base.metadata.create_all(bind=engine)` en el lifespan del backend | Crea tablas **faltantes** pero jamás altera existentes: no agrega columnas, índices, constraints ni triggers. | `backend/app/main.py:38` |
| D-3 | Parche `ALTER TABLE public.usuarios ADD COLUMN IF NOT EXISTS codalm` hardcodeado en el lifespan | Prueba viviente de que D-2 no alcanza. Cada cambio futuro requeriría otro parche igual, acumulándose en `main.py`. | `backend/app/main.py:42-45` |
| D-4 | **Dos fuentes de verdad divergentes:** `edw/07` declara triggers (`set_updated_at`), `COMMENT ON` e índices parciales que los modelos SQLAlchemy no expresan; los modelos declaran defaults de aplicación que el SQL no ve. El propio `edw/07` lo admite: "ambos caminos deben mantenerse sincronizados" (a mano). | Drift silencioso: una instalación desde cero (07) y una incremental (`create_all`) producen esquemas distintos. | `edw/07_public_app_tables.sql:111-113` |
| D-5 | El seed (roles + usuarios con hash bcrypt fijo) solo existe en `edw/08`, atado al initdb del volumen nuevo. | En una BD existente donde se agrega una tabla nueva con FK a `roles(nombre)` (p.ej. `notificaciones`), el seed nunca corre por sí solo. | `edw/08_seed_roles_usuarios.sql` |

**Solución propuesta:** adoptar **Alembic** (sistema de migraciones oficial de SQLAlchemy, ya en el stack) como **único dueño del esquema `public`**. Cada cambio de esquema pasa a ser un script versionado en git que se aplica automáticamente en cualquier entorno — volumen nuevo o BD viva — al arrancar el backend.

## 1. Fase 0 — Auditoría previa (entregable: `docs/auditoria/37_migraciones_esquema_public.md`)

Es el paso crítico: la migración *baseline* debe calzar **exactamente** con lo que existe en las BDs reales, o el primer `--autogenerate` propondrá "correcciones" espurias.

1. **Comparación tabla por tabla** de las 13 tablas `public.*` en tres frentes: (a) DDL de `edw/07`, (b) modelos SQLAlchemy registrados en `app/database/base.py`, (c) esquema real de la BD de desarrollo (`\d+` vía psql contra `postgres_edw`). Documentar cada divergencia (tipos, nullability, `server_default` vs default de aplicación, índices, constraints con nombre, triggers).
2. **Inventario de objetos no-tabla:** función/trigger `public.set_updated_at`, índice parcial `uq_comision_config_vendedor_vigente` (WHERE `vigente_hasta IS NULL`), CHECKs con nombre, `COMMENT ON`. Alembic autogenerate no los captura — deben ir como `op.execute()` en la baseline.
3. **Clasificación de datos por tabla** (qué viaja a producción — ver matriz en Fase 3).
4. **Verificar quién más escribe en `public`:** el ETL escribe `cliente_lookup` y potencialmente `metas_comerciales_operativas` sin pasar por el backend → confirmar el orden de arranque requerido en producción (migraciones antes de la primera corrida del ETL).

## 2. Fase 1 — Introducir Alembic (dueño del esquema `public`)

1. `alembic` en `backend/requirements.txt`; `alembic init alembic` dentro de `backend/`.
2. `alembic/env.py`:
   - URL de conexión desde `app.core.config.settings` (mismo `DATABASE_URL` que el backend) — **nunca** credenciales en `alembic.ini`.
   - `target_metadata = Base.metadata` importando `app.database.base` (los 13 modelos ya registrados).
   - `include_object` que **excluya todo lo que no sea esquema `public`**: los esquemas `edw.*` y `ml.*` son del ETL; Alembic jamás debe proponer tocarlos ni "detectar" sus tablas como huérfanas.
3. **Migración baseline `0001_baseline_public`:** reproduce el estado real auditado en Fase 0 (tablas + índices + trigger + comments vía `op.execute`). Su `downgrade` es `NotImplementedError` deliberado (no se destruye la base de la app).
4. **Migración de datos `0002_seed_roles`:** los 4 roles con `INSERT ... ON CONFLICT (nombre) DO NOTHING` (idempotente, reemplaza la parte de catálogo de `edw/08`). El usuario admin inicial se seedea con contraseña desde variable de entorno (`ADMIN_INITIAL_PASSWORD`), **no** con el hash bcrypt fijo versionado en `edw/08` — en producción ese hash conocido es una puerta trasera.

## 3. Fase 2 — Aplicación automática en el arranque (dev y producción)

1. **Entrypoint del contenedor backend** (script previo a uvicorn, recomendado sobre hacerlo en el lifespan: falla rápido y la API nunca arranca con esquema viejo):
   - Si no existe `public.alembic_version` **y** existe `public.usuarios` → BD pre-Alembic (dev actual o prod inicializada con `edw/07`): `alembic stamp 0001_baseline_public`, luego `alembic upgrade head`.
   - Si la BD está vacía → `alembic upgrade head` crea todo desde cero.
   - Si ya está sellada → `alembic upgrade head` aplica solo lo pendiente (no-op si está al día).
2. **Retirar de `main.py`:** el `Base.metadata.create_all` y el `ALTER TABLE ... codalm` hardcodeado (D-2/D-3). El lifespan queda solo con `validar_configuracion` + `ModelLoader`.
3. **Cambio de rol de `edw/07` y `edw/08`:** dejan de ser fuente de verdad del esquema `public`. Opciones: (a) retirarlos del initdb y que Alembic cree todo (recomendado — una sola fuente de verdad), o (b) conservarlos para bootstrap de volumen nuevo y que el entrypoint selle con `stamp`. Decisión a confirmar en Fase 0 según cómo dependa el orden initdb→ETL. En ambos casos se les añade cabecera "REFERENCIA — la fuente de verdad es `backend/alembic/`".
4. **`docker-compose.yml`:** documentar/garantizar el orden `postgres_edw` (healthcheck) → migraciones (entrypoint backend) → primera corrida manual del ETL.

## 4. Fase 3 — Datos: qué viaja de dev a producción

| Categoría | Tablas | Estrategia |
|---|---|---|
| Catálogo/seed | `roles` | Migración de datos idempotente (Fase 1, punto 4) |
| Usuario inicial | `usuarios` (solo el admin) | Seed con password desde env var; el resto de usuarios se crean en prod vía UI. **No copiar hashes de dev.** |
| Configuración de negocio | `comision_matriz_categorias`, `comision_factores_credito`, `comision_config_vendedor` | Seed de defaults vía migración de datos si gerencia los define; ajustes en prod vía la UI existente (`/gerencia/goals/commission-config/*`) |
| Regenerable en prod | `cliente_lookup`, `metas_comerciales_operativas` | **No copiar:** `cliente_lookup` la puebla el ETL con el `PII_SALT` de producción (copiarla rompería la correspondencia de hashes); las metas se generan con `POST /gerencia/goals/generate` sobre el EDW de prod |
| Nace vacía | `recomendaciones_eventos`, `notificaciones`, `comision_liquidaciones`, `gestion_cartera_eventos`, `anomalias_revisiones`, `intentos_login_fallidos` | Solo esquema; datos operativos nacen en prod |

## 5. Fase 4 — Flujo de trabajo nuevo y validación

1. **Flujo para todo cambio de esquema `public` en adelante:** modificar el modelo SQLAlchemy → `alembic revision --autogenerate -m "..."` → **revisar a mano** el script generado → commit. El deploy aplica la migración solo por arrancar el contenedor. Documentarlo en CLAUDE.md §Convenciones.
2. **Test de guardia** en `backend/tests/`: `alembic check` (o `compare_metadata`) contra una BD efímera — falla si alguien cambió un modelo sin generar migración (mata el drift D-4 de raíz).
3. **Test del camino de adopción:** BD creada solo con `edw/07` → entrypoint → verifica `stamp` + `upgrade` sin error ni cambios destructivos.
4. **Prueba de humo end-to-end:** volumen nuevo → arranque completo compose → login con el admin seedeado → smoke de un endpoint por rol.
5. **Documentación:** actualizar `docs/deploy/instalacion_windows_server_paso_a_paso.md` (retirar pasos manuales de DDL de `public`), CLAUDE.md (§Arquitectura, §Restricciones "los DDL de edw/ solo corren en volumen nuevo" — matizar que ya no aplica a `public`, §Riesgos D-2/D-3 resueltos) y la auditoría 37 con lo aplicado.

## 6. Riesgos y salvaguardas

- **Baseline desalineada (riesgo #1):** si `0001_baseline` no calza con la BD real, todo autogenerate futuro arrastra ruido. Mitigación: la comparación de Fase 0 es bloqueante; validar con `alembic check` contra la BD de dev recién sellada.
- **Alembic tocando `edw.*`:** un `include_object` mal configurado podría proponer DROP de las tablas del DW (no están en `Base.metadata`). Mitigación: filtro por esquema + test que asserta que un autogenerate en limpio produce migración vacía.
- **Orden migraciones ↔ ETL en prod:** el ETL escribe `public.cliente_lookup`; si corre antes que las migraciones en una BD vacía, falla. Mitigación: Fase 2 punto 4 + nota en el workflow `.agent/workflows/ejecutar-etl.md`.
- **Hash del admin versionado en `edw/08`:** al convertir el seed a migración se elimina el hash fijo del camino de producción; queda pendiente (relacionado, no bloqueante) el retiro de `docs/credenciales_sistema.md` ya diferido por decisión del usuario.
- **Producción SAP:** este plan no toca el ERP en absoluto (solo PostgreSQL `public`).

**Reglas transversales:** sin hardcodes (config por env vars), excepciones de dominio, Producción SAP solo lectura, auditoría antes de código, actualizar `02_reglas_negocio_validadas.md` si surge regla nueva.
