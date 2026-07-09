# Auditoría 2 — Núcleo Python del Pipeline ETL (orchestrator, loaders, connectors, config)

- **Alcance:** `etl/` completo, segunda pasada tras `01_auditoria_extractores.md`/`03_cambios_aplicados.md` (misma fecha).
- **Fecha:** 2026-07-08
- **Modo:** SOLO LECTURA sobre Producción (no aplica en esta pasada: no se ejecutó SQL contra SAP). Se revisó código estático únicamente.
- **Objetivo:** cerrar hallazgos que la ronda anterior dejó fuera de foco (esa ronda se centró en los extractores SQL y en C1/C2/PII/rendimiento). Esta ronda revisa `orchestrator.py`, `loaders/`, `connectors/postgres_connector.py`, `transformers/`, `config/settings.py` y los 24 extractores para hardcodes/consistencia.
- **Resultado clave:** **no hay ninguna escritura a Producción.** Todo lo que toca SAP vía `sqlany_connector.py` es `SELECT`; todo `INSERT/UPDATE/DELETE/TRUNCATE` observado apunta exclusivamente al EDW PostgreSQL. Los hallazgos son de correctitud/robustez y hardcodes, no de la regla "producción de solo lectura".

---

## Hallazgos

### High

**H1 — Extractores "cabecera" huérfanos con hardcode, no conectados al pipeline**
`etl/extractors/facturas_cabecera_extractor.sql`, `compras_cabecera_extractor.sql`, `devoluciones_cabecera_extractor.sql`.
Ninguno está referenciado en `PIPELINE_CONFIG` (`orchestrator.py`); la lógica activa de facturación/compras/devoluciones vive en los `*_detalle_extractor.sql`, que sí usan los tokens `{CODEMP}`/`{ESTADO}` parametrizados por la ronda anterior. Estos 3 archivos quedaron con `codemp = '01'` y (en facturas) `estado = 'P'` literales — código muerto con hardcode, contradice el patrón ya corregido en el resto del proyecto.
**Acción:** eliminados (dead code).

**H2 — Fallback silencioso a fila arbitraria al resolver llaves foráneas (`resolver_llaves_hecho`)**
`orchestrator.py` (bloque de resolución de SKs): si falta la columna `establ` en el hecho, se toma `sucursal_sk` de un `SELECT ... LIMIT 1` arbitrario; y si a cualquier SK le faltan valores y no existe la fila default `-1` en la dimensión, también se recurre a `LIMIT 1`. Esto puede atribuir silenciosamente una transacción real a un cliente/producto/sucursal incorrecto, sin registrar cuántas filas se vieron afectadas.
**Acción:** se eliminó el fallback `LIMIT 1` arbitrario; solo se usa el default explícito `-1` si existe. Si quedan SKs nulos sin default, se loguea `WARNING` con el conteo de filas afectadas por columna antes de cargar.

**H3 — `load_dim_scd2` trata cualquier excepción como "tabla nueva"**
`etl/loaders/dim_loader.py`: el `SELECT` de vigentes actuales estaba envuelto en `except Exception` genérico, así que un error de permisos/conectividad/typo se interpretaba igual que "la tabla aún no existe", y todas las filas vigentes se reinsertaban como "nuevas", duplicando el historial SCD2 activo.
**Acción:** se reemplazó por una verificación explícita de existencia de tabla (`sqlalchemy.inspect(engine).has_table(...)`). Si la tabla existe y la consulta falla, la excepción se propaga (la aísla el `try/except` por tabla que ya existe en el orquestador).

**H4 — Código muerto duplicado de idempotencia**
`etl/loaders/fact_loader.py::load_facts_incremental` no se usa en ningún lado — ya estaba señalado como "código muerto" en `01_auditoria_extractores.md §1` pero no se había retirado. `orchestrator.py` reimplementa la misma lógica de borrado+insert inline. Dos implementaciones divergentes del mismo concepto son riesgo de deriva si se corrige una y no la otra.
**Acción:** eliminada la función muerta.

**H5 — Columnas descartadas silenciosamente por drift de esquema**
`etl/connectors/postgres_connector.py::load_dataframe`: si el DataFrame trae columnas ausentes en la tabla destino, se filtran sin loguear cuáles ni cuántas — un cambio de esquema no propagado perdería datos sin ninguna traza.
**Acción:** se agregó `WARNING` con tabla + columnas descartadas cuando aplica.

### Medium

**M1 — `PG_SCHEMA` hardcodeado a `'public'` inline** (`orchestrator.py`, carga de `cliente_lookup`). Se extrajo a constante nombrada con comentario de por qué ese lookup vive fuera del schema `edw`.

**M2 — `chunksize=5000` hardcodeado en 3 llamadas `to_sql`** (`postgres_connector.py`), mientras `config.BATCH_SIZE` ya existe y se usa en el lado de extracción. Se unificó a `self.config.BATCH_SIZE`.

**M3 — Rango de `Dim_Tiempo` (2010–2030) hardcodeado como default de función** (`transformers/dim_tiempo.py`). Cualquier fecha fuera de rango no resuelve `fecha_sk` (cae en el defecto de H2). Se movió a `config.DIM_TIEMPO_DESDE`/`DIM_TIEMPO_HASTA`, pasado explícitamente desde el orquestador.

**M4 — `DB_USER` con default hardcodeado `"dba"`** (`config/settings.py`), la cuenta privilegiada por convención en SQL Anywhere: si falta `.env`, el pipeline intentaría conectar silenciosamente como `dba` en vez de fallar rápido. Se quitó el default (queda `""`, igual que `DB_PASSWORD`/`DB_SERVER`).

**M5 — Excepciones amplias en `get_last_etl_date`/`registrar_control_etl`** (`orchestrator.py`): cualquier error se trataba igual que "primera corrida". Se diferenció explícitamente "tabla `etl_control` no existe todavía" (vía `has_table`) de cualquier otro error, que ahora se loguea en `ERROR` con `exc_info=True`.

---

## Fuera de alcance (documentado, no corregido en esta ronda)

- **SCD inconsistente en `dim_vendedor`/`dim_empleado`:** tienen `delta_col` en `PIPELINE_CONFIG` pero usan loader `'dim'` (upsert plano) en vez de `'scd2'`, así que cambios de atributo (comisión, departamento) se sobrescriben sin dejar historial. Corregirlo requiere que esas tablas del EDW tengan columnas `es_vigente`/`fecha_fin_vigencia` — cambio de esquema (DDL) del EDW, fuera del alcance "sin tocar DDL" de esta ronda (mismo criterio aplicado a `transferencias_extractor.sql` en `03_cambios_aplicados.md §5`).
- **Sin validación de calidad de datos pre/post carga** (conteos, nulos, esquema): es una funcionalidad nueva, no un bug puntual. Recomendado como trabajo futuro.
- **Hallazgos Low** (excepciones silenciosas en scripts de diagnóstico `inspect_formapago.py`/`test_sap.py`, ruta relativa de `.env`, literal `_PII_SALT_INSEGURO` como centinela intencional): no se tocan, son scripts auxiliares o comportamiento a propósito.

## Verificación

- `py_compile` sobre todos los módulos Python modificados.
- Confirmado por `grep` que `load_facts_incremental` no tenía otro uso antes de eliminarla.
- Confirmado que los 3 extractores `_cabecera` no estaban en `PIPELINE_CONFIG` antes de eliminarlos.
- **Limitación:** no se pudo probar la carga end-to-end contra el EDW real en este entorno (credenciales `PG_PASSWORD=CHANGE_ME`), misma limitación que `03_cambios_aplicados.md §7`.
