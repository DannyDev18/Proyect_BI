# 13 — Impacto de `dim_estado_documento` sobre backend y ML (verificación previa a Fase 2)

- **Fecha:** 2026-07-09
- **Alcance:** verificación del DDL nuevo de `edw/` ya aplicado a la BD de desarrollo (`bi_postgres_edw`), y su impacto sobre todo el SQL que aún referencia las columnas eliminadas de `fact_ventas_detalle`. Motivada por el inicio de la Fase 2 del plan de reconstrucción ML (`docs/auditoria/12_fase0_analisis_capa_contratos_ml.md` §6).
- **Método:** `SELECT` contra el EDW (`docker exec bi_postgres_edw psql`), revisión estática de `etl/transformers/fact_transformer.py`, `ml/src/data/make_dataset.py` y `backend/app/repositories/*.py`. Ninguna escritura a Producción ni al EDW.

## Hallazgos

### Alto — H13-01 El DDL nuevo YA está aplicado y cargado en `bi_postgres_edw`
- **Evidencia:** `\dt edw.*` lista `dim_estado_documento` (24 tablas totales); `fact_ventas_detalle` ya no tiene columnas `es_devolucion`/`estado_factura`/`tipo_documento`, solo `estado_documento_sk` (FK NOT NULL). `fecha_carga` de las 520.760 filas es un único timestamp (`2026-07-09 17:07:51`): recarga reciente y completa, no un residuo parcial.
- **Impacto:** el supuesto de la auditoría 12 ("el DDL nuevo aún no está commiteado ni aplicado a una BD existente") ya no aplica al entorno de desarrollo actual — cualquier SQL que siga usando las columnas viejas falla en ejecución, no es una advertencia teórica.
- **Recomendación:** tratar todo el SQL listado en H13-02 como roto AHORA, no como deuda futura.

### Alto — H13-02 Blast radius más amplio que el documentado en la auditoría 12: no solo ML
- **Evidencia (`grep estado_factura|es_devolucion|tipo_documento`):**
  | Archivo | Línea(s) | Uso |
  |---|---|---|
  | `ml/src/data/make_dataset.py` | 117 (`fetch_market_basket`) | `WHERE NOT fvd.es_devolucion` |
  | `ml/src/data/make_dataset.py` | 153 (`fetch_goals_data`) | `WHERE f.estado_factura != 'I'` |
  | `backend/app/repositories/dataset_repository.py` | 33, 51 | `WHERE v.estado_factura != 'I'` |
  | `backend/app/repositories/prediction_repository.py` | 50, 67, 89, 109 | `estado_factura != 'I'`, `CASE WHEN es_devolucion THEN...` |
  | `backend/app/repositories/analytics_repository.py` | 137, 259, 268 | `f.estado_factura = 'P'` |
  | `backend/app/repositories/goal_repository.py` | 50 | `f.estado_factura = 'P'` |

  La auditoría 12 (§3.2) solo documentó `dataset_repository.py` y `prediction_repository.py` como rotos por C-1. **`analytics_repository.py` y `goal_repository.py` también están rotos** y no forman parte del alcance ML — son el backend de los dashboards de Gerencia y de Metas, fuera del plan de contratos ML.
- **Impacto:** con el DDL ya cargado (H13-01), cualquier endpoint que ejecute estas queries falla con `column "estado_factura" does not exist`. Esto afecta directamente a producción/desarrollo del backend, no solo a un futuro reentrenamiento de modelos.
- **Riesgo:** si la Fase 2 del plan ML se ejecuta con el alcance original (solo `make_dataset.py` + `dataset_repository.py` + `prediction_repository.py`), `analytics_repository.py` y `goal_repository.py` seguirán rotos.
- **Recomendación:** decidir explícitamente el alcance antes de tocar código (ver sección de decisión más abajo). No es una recomendación de "arreglarlo ya" unilateral — es una pregunta de alcance para el usuario, dado que estos dos archivos están fuera del plan de contratos ML que se venía ejecutando.

### Medio — H13-03 Estructura real de `dim_estado_documento`
- **Evidencia:**
  ```
  estado_documento_sk (PK, SERIAL) | tipo_documento VARCHAR(5) | es_devolucion BOOLEAN NOT NULL | estado_factura VARCHAR(1) NOT NULL
  UNIQUE (tipo_documento, es_devolucion, estado_factura)
  ```
  Filas actuales: `(-1, '-1', false, 'A')` (centinela) y `(1, 'F', false, 'P')` (única combinación real cargada). `fact_ventas_detalle.estado_documento_sk` es FK NOT NULL hacia esta dimensión.
- **Contraste con `etl/transformers/fact_transformer.py:68-84`:** el transformer calcula `es_devolucion = cantidad < 0` (marcado "Pendiente de validar", auditoría 08 F13/F14) y expone `tipo_documento`/`estado_factura` con nombres exactos para que el **loader** (no visible en este repo — `etl/loaders/` está borrado del working tree, ver riesgo ya documentado en CLAUDE.md) resuelva el `estado_documento_sk` contra esta dimensión tipo junk dimension.
- **Por qué solo hay una combinación cargada:** el extractor de ventas ya filtra `estado = ESTADO_VALIDO` ('P') a nivel SQL (regla de negocio 1) y `fact_ventas_detalle` no incluye devoluciones (que van a `fact_devoluciones`, tabla separada) — así que hoy `es_devolucion` es efectivamente siempre `false` para este hecho. El filtro contra `dim_estado_documento` es hoy un no-op semántico pero necesario defensivamente (excluir el centinela `-1`, que señalaría una falla de resolución del loader) y por completitud a futuro si el negocio de "estado" se amplía.
- **Recomendación para el JOIN correcto:** `JOIN edw.dim_estado_documento ed ON fvd.estado_documento_sk = ed.estado_documento_sk WHERE ed.estado_documento_sk <> -1` reproduce "documento válido, sin fallas de resolución"; agregar `AND NOT ed.es_devolucion` donde el hallazgo original (H-15, auditoría 11) pedía excluir devoluciones explícitamente (defensivo, no cambia el resultado con los datos actuales).

### Bajo — H13-04 `fetch_transactions_for_anomalies` filtra sobre un centinela que ya no existe como tal
- **Evidencia:** `ml/src/data/make_dataset.py:135` filtra `WHERE pct_margen > -9999`, heredado de cuando `-9999.9999` era un centinela de "sin costo" (auditoría 05, DQ-1). Con el DDL nuevo, `etl/transformers/fact_transformer.py:53-61` ya no usa `-9999` como centinela: `pct_margen` es `0.0` por convención (subtotal_neto=0 o margen_bruto NULL) y se **clipea** a `[-9999.9999, 9999.9999]` solo como límite numérico de la columna `NUMERIC(8,4)`, no como marca de calidad.
- **Impacto:** el filtro legacy podría excluir por error una transacción con margen genuinamente extremo que clipea justo en el límite (`-9999.9999`), tratándola como si fuera el viejo centinela. Con los datos actuales el mínimo real es exactamente `-9999.9999` (verificado por consulta), así que el filtro **sí está excluyendo filas hoy**, aunque no se puede determinar desde SQL si son casos de clip genuino o coincidencia — no hay forma de distinguirlos post-clip.
- **Recomendación:** eliminar el filtro `pct_margen > -9999` (ya no aplica, C-3 de la auditoría 12); si se quiere excluir out-of-range extremos, usar el propio `costo_total IS NOT NULL` como criterio de calidad (alineado con la política de nulos que el contrato `anomalies.json` ya deja pendiente de decisión).

## Verificaciones automáticas mínimas ejecutadas

1. **Pérdida de registros:** N/A (no se movieron datos en esta verificación).
2. **Duplicados en `dim_estado_documento`:** ninguno — `UNIQUE(tipo_documento, es_devolucion, estado_factura)` + 2 filas totales.
3. **Volumen:** `fact_ventas_detalle` = 520.760 filas, una sola carga (`fecha_carga` constante) — consistente con recarga completa reciente.
4. **Llaves huérfanas / centinela:** 0 filas con `estado_documento_sk = -1` en `fact_ventas_detalle` (100% resueltas contra la dimensión real).
5. **`costo_total`/`margen_bruto` NULL reales (cambio C-2):** 58.121 de 520.760 filas (11.2%) sin costo — confirma que el NULL real ya está en los datos, no es un caso hipotético para el contrato de anomalías.

## Resumen de recomendaciones por prioridad

- **Alta:** decidir alcance de la Fase 2 (ver decisión pendiente abajo) antes de escribir código — el hallazgo H13-02 amplía el radio de impacto más allá del plan ML original.
- **Alta:** reescribir `ml/src/data/make_dataset.py` (`fetch_market_basket`, `fetch_goals_data`) y `backend/app/repositories/{dataset_repository,prediction_repository}.py` contra `dim_estado_documento` — alcance ya confirmado en doc 12.
- **Media:** si se amplía el alcance, `analytics_repository.py` y `goal_repository.py` necesitan el mismo cambio de `f.estado_factura = 'P'` a un JOIN con `dim_estado_documento` (semánticamente hoy es un no-op, pero el SQL literal falla en ejecución).
- **Baja:** quitar el filtro obsoleto `pct_margen > -9999` en `fetch_transactions_for_anomalies` (H13-04).

## Decisión pendiente (bloqueante para continuar la Fase 2)

El plan de la auditoría 12 acota la Fase 2 a `make_dataset.py` + `dataset_repository.py` + `prediction_repository.py` (contrato ML). Pero `analytics_repository.py` (Gerencia) y `goal_repository.py` (Metas) están **igual de rotos** contra el DDL ya cargado, y no son parte del alcance ML. Ver pregunta al usuario en el mensaje de esta conversación.
