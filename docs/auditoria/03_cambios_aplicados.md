# Cambios Aplicados al Extractor ETL

- **Fecha:** 2026-07-08
- **Alcance aprobado:** *"Todo lo aplicable sin tocar DDL"* + validación contra Producción por `SELECT`.
- **Base:** [01_auditoria_extractores.md](01_auditoria_extractores.md) (hallazgos) y [02_reglas_negocio_validadas.md](02_reglas_negocio_validadas.md) (reglas confirmadas contra SAP).
- **Regla respetada:** Producción de solo lectura. Ninguna escritura al ERP. Sin cambios de esquema (DDL) del DW.

---

## 1. Resumen

Se corrigieron 2 bugs críticos de correctitud, se robusteció la carga incremental y la parametrización, y se **activó el snapshot de inventario** (antes nunca poblado). Todos los extractores (24 = 22 + 2 nuevos) fueron **verificados ejecutándose contra SAP** con los tokens renderizados (24/24 OK). El código Python compila (`py_compile` OK).

---

## 2. Cambios de correctitud (críticos)

### C1 — Idempotencia de hechos (duplicación) — CORREGIDO
`etl/orchestrator.py`. El DELETE de idempotencia comparaba `fecha_sk >= YYYYMMDD` contra un `SERIAL`, por lo que **nunca borraba** y el `append` duplicaba en cada corrida. Ahora borra por la **fecha real** vía `dim_fecha`:
```sql
DELETE FROM edw.<tabla>
WHERE fecha_sk IN (SELECT fecha_sk FROM edw.dim_fecha WHERE fecha_completa >= :desde)
```

### C2 — Inyección del filtro incremental (UNION ALL) — CORREGIDO
Se eliminó el frágil `sql_query.replace(';', ...)` (que en los `UNION ALL` sólo filtraba la última rama). Ahora cada extractor declara **tokens explícitos** que el orquestador renderiza con `render_sql()`:
- `{CODEMP}` → `config.CODEMP`
- `{ESTADO}` → `config.ESTADO_VALIDO`
- `{FECHA_DESDE}` → fecha incremental (última corrida OK) o histórica (`config.FECHA_HISTORICA`, full).

Cada rama del `UNION ALL` lleva su **propio** `AND <col> >= '{FECHA_DESDE}'`, por lo que el filtro aplica a todas las ramas. El token usa **columnas reales** del origen (no alias), corrigiendo además la carga incremental de `nomina`/`caja`/`metas` que antes referenciaba alias (`fecdoc`/`fecape`/`fecmes`) y habría fallado en el `WHERE`.

### BONUS — `es_entrada`/`es_salida` del Kardex — CORREGIDO
`etl/transformers/fact_transformer.py`. Como `cantot` **siempre es positivo** (validado §4), la regla anterior `es_entrada = cantidad > 0` marcaba **todo** como entrada. Ahora se deriva de `tipdoc` (`EN`/`AC` = entrada, `SA`/`AD` = salida). Requirió exponer `tipdoc` en `kardex_extractor.sql`.

---

## 3. Parametrización (C4) y calidad

- **`codemp` parametrizado** en los 22 extractores (`'01'` → `'{CODEMP}'`), incluida la dimensión estática `formapago`.
- **`estado` parametrizado** (`'P'` → `'{ESTADO}'`) en ventas/devoluciones; significado documentado (P=Procesada, A=Anulada) — §1.
- **`kardex_extractor.sql`**: se añadieron `tipdoc` (dirección) y `establ` (permite **resolver la sucursal**, antes ausente → todos los movimientos caían en la sucursal por defecto).
- **`facturas_detalle_extractor.sql`**: `poriva` protegido con `COALESCE(e.poriva, 0)` para no propagar NULL al IVA/total.
- **`almacenes_extractor.sql`**: `establ` inferido ahora **determinista** (tie-break `…, establ ASC`) — evita resultados no reproducibles ante empates (§A4).

---

## 4. Robustez, rendimiento y seguridad (P9/P10)

`etl/orchestrator.py` y `etl/config/settings.py`:
- **P10 · Aislamiento por tabla:** cada tabla corre en su propio `try/except`; un fallo registra `FAIL` individual en `edw.etl_control` y **continúa** con las demás (antes abortaba todo). Resumen final `N OK / M FAIL`.
- **P9 · Caché de dimensiones:** `resolver_llaves_hecho` releía las `dim_*` completas **por cada chunk**; ahora se cachean una vez por corrida (`_leer_dim_cacheada`).
- **BATCH_SIZE:** la extracción usa `config.BATCH_SIZE` (antes `10000` hardcodeado).
- **PII_SALT obligatorio:** `validar_configuracion()` **aborta** el pipeline si el salt está vacío o es el valor inseguro heredado (evita hashes de cliente re-identificables). Definir `PII_SALT` en `.env`.

---

## 5. Nuevos extractores (inventario / reposición)

### `existencias_extractor.sql` — snapshot de stock (ACTIVADO)
Fuente validada `vi_mv_existencias` + costo desde `articulos.ultcos`. Se **conectó** a la tabla ya existente `edw.Fact_Inventario_Snapshot` (que nunca se poblaba) mediante el transformer ya presente `transformar_inventario_snapshot`. Idempotencia de snapshot: reemplaza **sólo la foto de hoy** (preserva el histórico), vía `'snapshot': True` en `PIPELINE_CONFIG`.
- Pendiente [maestro]: `stock_minimo`, `stock_maximo`, `punto_reorden` quedan en `0.0` (no hay maestro de mínimos/máximos en el origen).

### `transferencias_extractor.sql` — transferencias entre bodegas (VALIDADO, NO conectado)
Deriva transferencias del kardex (`tiporg='TRA'`) pareando por `(numdoc, numren, codart)`: `tipdoc='SA'`=origen, `tipdoc='EN'`=destino, `cantot`=cantidad enviada (regla validada §5). Ejecuta correctamente contra SAP.
- **No se conecta al pipeline** porque **no existe** una tabla `edw.Fact_Transferencias` (crearla es DDL, fuera del alcance). Queda listo para conectarse cuando se cree.
- Pendiente [ERP]: el origen no expone *cantidad solicitada* ni *estado* de la transferencia.

---

## 6. C3 y alias engañosos — decisión documentada (sin cambio de código)

- **C3 (signo de devoluciones):** se verificó que `fact_ventas_detalle` es la **fuente de verdad de ventas netas** que consume el backend (`prediction_service`/`analytics_service` usan `es_devolucion`), y que `fact_devoluciones` **no lo consume nadie**. Cambiar el signo rompería los dashboards/predicciones. **Convención documentada:** `fact_ventas_detalle` ya está neteada (F positivo, NC negativo con `es_devolucion`); `fact_devoluciones` es un hecho independiente de magnitudes positivas y **no debe sumarse** con ventas. No se alteraron signos.
- **Alias engañosos** (`ultcos AS costo_promedio`, `totfac AS costo_total_devolucion`, `totegr AS descuento_seguro`, `valcob AS valor_pagado`): sus nombres coinciden con **columnas del DW**; renombrarlos sin cambiar el DDL provocaría que la carga los descarte (pérdida de dato). Se **documentó** el significado real en comentarios del SQL y en §9 de las reglas; el renombrado queda como cambio de DDL futuro.

---

## 7. Verificación realizada

| Verificación | Resultado |
|---|---|
| `py_compile` de orchestrator/settings/transformers/loaders/connector | **OK** |
| Ejecución de los 24 extractores renderizados contra SAP (TOP 5, read-only) | **24/24 OK** |
| Reglas de negocio (tiporg, tipdoc, estado, existencias, unicidad, desinv) | validadas por `SELECT` (§ doc 02) |
| Sin NULL en columnas de fecha usadas como filtro (caja/…); metas y geografia vacíos en origen | confirmado (no hay regresión) |

**Limitación:** la carga **end-to-end contra el EDW PostgreSQL no pudo integrarse-probar** aquí porque este entorno no tiene credenciales del EDW (`PG_PASSWORD=CHANGE_ME`). Las correcciones C1/C2/P9/P10 y el wiring del snapshot deben ejecutarse una vez en el entorno destino y verificarse con:
```sql
-- Duplicados de hechos (debe ser 0 tras corrida incremental repetida):
SELECT fecha_sk, producto_sk, num_factura, COUNT(*) 
FROM edw.fact_ventas_detalle GROUP BY 1,2,3 HAVING COUNT(*)>1;
-- Snapshot poblado:
SELECT COUNT(*), MAX(fecha_sk) FROM edw.fact_inventario_snapshot;
-- Dirección de movimientos correcta:
SELECT es_entrada, es_salida, COUNT(*) FROM edw.fact_movimientos_inventario GROUP BY 1,2;
```

---

## 8. Archivos modificados / creados

**Modificados (Python):** `etl/orchestrator.py`, `etl/config/settings.py`, `etl/transformers/fact_transformer.py`.
**Modificados (SQL, 20):** todos los `etl/extractors/*.sql` (tokens `{CODEMP}`/`{ESTADO}`/`{FECHA_DESDE}`), con enriquecimiento en `kardex`, `facturas_detalle`, `articulos`, `almacenes`.
**Nuevos (SQL):** `etl/extractors/existencias_extractor.sql`, `etl/extractors/transferencias_extractor.sql`.
**Documentación:** `docs/auditoria/00_planificacion.md`, `01_auditoria_extractores.md`, `02_reglas_negocio_validadas.md`, `03_cambios_aplicados.md`.

**Nota de mantenimiento:** la clave `delta_col` en `PIPELINE_CONFIG` quedó **obsoleta** (reemplazada por el token `{FECHA_DESDE}` en el SQL); se conserva sin efecto para no alterar la estructura; puede retirarse en una limpieza posterior.
