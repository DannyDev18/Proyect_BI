# Auditoría 18 — `almacen_sk` ausente en `edw.fact_ventas_detalle` (columna en el DDL, no aplicada en la BD viva)

- **Fecha:** 2026-07-10
- **Alcance:** `edw/03_hechos.sql` (DDL de `Fact_Ventas_Detalle`), `etl/extractors/facturas_detalle_extractor.sql`,
  `etl/transformers/fact_transformer.py::transformar_ventas_detalle`, `etl/orchestrator.py`
  (`resolver_llaves_hecho`, `PIPELINE_CONFIG`), `etl/loaders/fact_loader.py`,
  `etl/connectors/postgres_connector.py::load_dataframe`, tabla `edw.fact_ventas_detalle` en el
  contenedor `bi_postgres_edw` (BD `edw`).
- **Método:** Revisión estática del código del ETL y del DDL versionado, más inspección directa
  del esquema real vía `docker exec bi_postgres_edw psql -U etl_user -d edw -c "\d edw.<tabla>"`
  y consultas `SELECT`/`COUNT(*)` de solo lectura contra el EDW (Postgres, no Producción SAP —
  no se ejecutó ninguna escritura contra SAP ni contra el EDW en esta fase de diagnóstico).

## Hallazgos

### Alta — H1: `codalm` sí llega correctamente hasta el DataFrame final, pero la tabla destino real no tiene columna para recibirlo
- **Evidencia:**
  - `etl/extractors/facturas_detalle_extractor.sql:10` selecciona `r.codalm` desde
    `renglonesfacturas` (confirmado: el campo existe en el origen SAP).
  - `etl/transformers/fact_transformer.py:19` normaliza `codalm` como llave de negocio
    (`normalizar_strings(df, [..., 'codalm', ...])`) sin descartarla.
  - `etl/orchestrator.py:372-378` (`resolver_llaves_hecho`, paso 9) resuelve `almacen_sk` desde
    `(codemp, codalm)` contra `edw.dim_almacen` para **cualquier** hecho cuyo DataFrame traiga
    `codalm` — `fact_ventas_detalle` incluida, vía `PIPELINE_CONFIG` (`orchestrator.py:278`,
    `depende_de: ['dim_producto', 'dim_cliente', 'dim_vendedor', 'dim_almacen', 'dim_sucursal']`).
  - `edw/03_hechos.sql:15` — el DDL versionado en el repo **ya declara**
    `almacen_sk INT NOT NULL REFERENCES edw.Dim_Almacen(almacen_sk)` en `Fact_Ventas_Detalle`.
  - Pero la tabla real en el contenedor (`docker exec bi_postgres_edw psql -U etl_user -d edw -c
    "\d edw.fact_ventas_detalle"`) **no tiene la columna `almacen_sk`** — el `\d` solo lista
    `venta_sk, fecha_sk, producto_sk, cliente_sk, sucursal_sk, vendedor_sk, formapago_sk,
    estado_documento_sk, num_factura, ..., fecha_carga`. Comparación directa: `fact_compras` y
    `fact_devoluciones` (creadas en el mismo `edw/03_hechos.sql`, con `almacen_sk NOT NULL`) **sí
    tienen la columna en vivo**, con su FK a `edw.dim_almacen` activa. Solo `fact_ventas_detalle`
    quedó desincronizada.
  - `etl/connectors/postgres_connector.py:55-70` (`load_dataframe`) filtra las columnas del
    DataFrame contra `inspector.get_columns(tabla, schema=schema)` de la tabla **real**, y
    descarta silenciosamente (con `logger.warning`, no error) cualquier columna que el
    DataFrame traiga pero la tabla destino no tenga. Como `almacen_sk` no existe en la tabla
    real, cada carga de `fact_ventas_detalle` la calcula correctamente en memoria y la descarta
    justo antes del `INSERT`.
- **Causa raíz:** el DDL de `edw/03_hechos.sql` fue actualizado (probablemente junto con la
  auditoría de diseño 07, que agregó `almacen_sk` a varios hechos por consistencia Kimball) pero,
  tal como advierte la sección "Restricciones" de `CLAUDE.md`, los DDL de `edw/` solo se aplican
  automáticamente al crear el volumen de Docker — un cambio de esquema en una BD ya existente
  requiere una migración manual que en este caso nunca se ejecutó para `fact_ventas_detalle`
  (sí se hizo, o la tabla se creó después, para `fact_compras`/`fact_devoluciones`).
- **Impacto:** las 520.760 filas actuales de `edw.fact_ventas_detalle` (`SELECT COUNT(*)`
  confirmado) no tienen ni pueden tener el almacén/bodega de la venta — imposibilita cualquier
  análisis de ventas por bodega/almacén (Gerencia, Bodega) a nivel de línea de venta, aunque el
  dato exista íntegro en SAP y el ETL ya lo procese.
- **Riesgos:**
  - Si se agrega la columna como `NOT NULL` directamente (igual que el DDL), el `ALTER TABLE`
    fallará contra las 520.760 filas existentes sin valor — hay que agregarla NULLABLE, hacer un
    backfill completo, y solo después aplicar el `NOT NULL`.
  - Un backfill mal alcanzado (solo incremental) dejaría el histórico previo con
    `almacen_sk IS NULL` de forma permanente, ya que `fact_ventas_detalle` es `fact_inc` con
    idempotencia por rango de fecha (`etl/orchestrator.py` DELETE `WHERE fecha_sk >= :desde`) —
    el próximo `MODO_INCREMENTAL=true` solo reprocesa desde el último `ultimo_etl_ok` exitoso
    (`edw.etl_control`: `2026-07-09 17:10:49`), no el histórico completo.
- **Recomendación:**
  1. `ALTER TABLE edw.fact_ventas_detalle ADD COLUMN almacen_sk INT REFERENCES edw.dim_almacen(almacen_sk);`
     (nullable primero).
  2. Backfill completo: correr el ETL solo para `fact_ventas_detalle`
     (`tablas_incluir=['fact_ventas_detalle']`) forzando modo `FULL`
     (`MODO_INCREMENTAL=false` para esa corrida) para que el DELETE+reload cubra todo el rango
     histórico (`FECHA_HISTORICA`, default `1900-01-01`) y `resolver_llaves_hecho` recalcule
     `almacen_sk` para las 520.760 filas.
  3. Validar 0 filas con `almacen_sk IS NULL` tras el backfill y medir el % que cae al
     centinela `-1` (llave huérfana `codalm` sin match en `dim_almacen`).
  4. Solo si el backfill deja 0 nulos, aplicar
     `ALTER TABLE edw.fact_ventas_detalle ALTER COLUMN almacen_sk SET NOT NULL;` para igualar
     el DDL versionado.
  5. (Opcional, consistencia con `fact_compras`/`fact_movimientos_inventario`) agregar un índice
     sobre `almacen_sk` si el patrón de consulta de Bodega/Gerencia lo requiere — no está en el
     DDL actual para este hecho, así que no es parte del hallazgo, solo una mejora de rendimiento
     a evaluar aparte.

## Validaciones automáticas mínimas ejecutadas

1. **Pérdida de registros:** N/A en esta fase (no se modificó la tabla aún). El conteo base es
   520.760 filas en `fact_ventas_detalle` — se revalidará igual después del backfill.
2. **Duplicados:** no aplica a este hallazgo (no cambia el grano de la tabla).
3. **Volumen entre cargas:** `edw.etl_control` muestra la última corrida exitosa
   (`SUCCESS`, 520.760 filas, `2026-07-09 17:10:49`) coincide con el conteo actual de la tabla —
   consistente, sin pérdida silenciosa previa.
4. **Cambio de granularidad:** no aplica — se agrega un atributo, no se cambia la clave del hecho.
5. **Llaves faltantes/huérfanas:** pendiente de medir hasta después del backfill (no existe la
   columna aún para evaluar el % de `-1`).
6. **Fechas fuera de rango:** no aplica a este hallazgo.
7. **Códigos inexistentes:** `dim_almacen` tiene 15 filas + el centinela `-1`
   (`(Desconocido)`, `codemp='-1'`, `codalm='-1'`, `establ='-1'`) ya sembrado — confirmado por
   `SELECT * FROM edw.dim_almacen WHERE almacen_sk = -1`.
8. **Integridad referencial:** `fact_compras` y `fact_devoluciones` sí tienen la FK
   `almacen_sk -> dim_almacen(almacen_sk)` activa en vivo, confirmando que el patrón de FK
   funciona en este EDW; el problema es exclusivo de `fact_ventas_detalle`.

## Resumen de recomendaciones por prioridad

| Prioridad | Acción |
|---|---|
| Alta | `ALTER TABLE` para agregar `almacen_sk` (nullable) + FK a `dim_almacen` en `fact_ventas_detalle`. |
| Alta | Backfill completo (modo FULL) de `fact_ventas_detalle` para poblar `almacen_sk` en las 520.760 filas existentes. |
| Alta | `SET NOT NULL` sobre `almacen_sk` una vez confirmado 0 nulos post-backfill, para igualar `edw/03_hechos.sql`. |
| Media | Evaluar si conviene un índice sobre `almacen_sk` en `fact_ventas_detalle` (no está en el DDL actual; no es parte de este hallazgo). |

## Resolución aplicada (2026-07-10)

El usuario decidió **no** aplicar `ALTER TABLE` sobre el contenedor actual: va a recrear el
volumen de Docker del EDW desde cero (`docker compose down -v` + `up` sobre `postgres_edw`, o
equivalente) para repoblar todo el DW desde SAP con el ETL completo.

Con esa ruta de remediación, se revisó el pipeline de extremo a extremo para confirmar que
**no falta ningún cambio de código** — la cadena `codalm` (SAP) → `almacen_sk` (EDW) ya está
completa desde la última vez que se tocó este código (auditoría 09/10):

- `etl/extractors/facturas_detalle_extractor.sql:10` ya trae `r.codalm`.
- `etl/transformers/fact_transformer.py:19` ya lo normaliza sin descartarlo.
- `etl/orchestrator.py` (`PIPELINE_CONFIG`, línea 278) ya declara `depende_de: [..., 'dim_almacen', ...]`
  para `fact_ventas_detalle`, y `dim_almacen` ya precede al hecho en la lista (`validar_orden_pipeline`
  no fallaría).
- `resolver_llaves_hecho()` (`etl/orchestrator.py:372-378`) ya resuelve `almacen_sk` genéricamente
  para cualquier hecho con columna `codalm`, incluida `fact_ventas_detalle`.
- `edw/03_hechos.sql:15` ya declara `almacen_sk INT NOT NULL REFERENCES edw.Dim_Almacen(almacen_sk)`.
- `get_last_etl_date()` devuelve `1900-01-01` cuando `edw.etl_control` no existe/está vacía (volumen
  nuevo), forzando modo `FULL` en la primera corrida — no se necesita ninguna variable de entorno
  especial para que la recarga desde cero sea completa.

**Conclusión: no se modificó ningún archivo de `etl/` ni `edw/` en esta auditoría.** El hallazgo
H1 (columna ausente en la BD viva) se resuelve por sí solo al recrear el volumen, porque
`edw/01..09` se ejecuta automáticamente en un volumen nuevo y ya contiene la columna correcta.
Validado con `python -m py_compile` sobre `orchestrator.py`, `transformers/fact_transformer.py`,
`loaders/fact_loader.py` y `connectors/postgres_connector.py` (sin errores).

### Checklist de verificación post-repoblación (ejecutar tras el `docker compose up` con volumen nuevo)

```sql
-- 1. La columna debe existir y ser NOT NULL
\d edw.fact_ventas_detalle

-- 2. Cero filas sin almacen_sk resuelto (no debería haber NULL; NOT NULL ya lo impediría a nivel de columna)
SELECT COUNT(*) FROM edw.fact_ventas_detalle WHERE almacen_sk IS NULL;

-- 3. % de filas cayendo al centinela -1 (codalm sin match en dim_almacen — llave huérfana)
SELECT
  COUNT(*) FILTER (WHERE almacen_sk = -1) AS huerfanas,
  COUNT(*) AS total,
  ROUND(100.0 * COUNT(*) FILTER (WHERE almacen_sk = -1) / COUNT(*), 2) AS pct_huerfanas
FROM edw.fact_ventas_detalle;

-- 4. Reconciliación de volumen contra la corrida anterior (esperado ~520,760 filas, salvo
--    cambios reales en SAP desde la última carga)
SELECT COUNT(*) FROM edw.fact_ventas_detalle;
```

Si el paso 3 muestra un porcentaje de huérfanas mayor a lo esperado, revisar si `dim_almacen`
terminó de cargar (15 filas + centinela `-1`, confirmado antes de recrear el volumen) antes de
que corriera `fact_ventas_detalle` — el orden en `PIPELINE_CONFIG` ya lo garantiza, pero vale la
pena confirmarlo en los logs de la corrida real.
