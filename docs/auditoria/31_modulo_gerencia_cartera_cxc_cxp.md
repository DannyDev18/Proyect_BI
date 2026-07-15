# Auditoría 31 — Validación de datos para el módulo Gerencia: Cartera y Flujo de Caja (CxC/CxP)

> **Estado (2026-07-14):** el módulo se implementó y se retiró después por decisión de producto
> (no por un problema de datos). Los fixes de ETL de H1/H2 (duplicación de `fact_pagos_cxp`,
> `fact_cobros_cxc.sucursal_sk` sin resolver) se mantienen aplicados en el EDW. El resto del
> contenido queda como registro histórico de la validación.

- **Fecha:** 2026-07-14 (actualizado el mismo día tras aplicar los fixes de H1/H2)
- **Alcance:** `edw.fact_cobros_cxc`, `edw.fact_pagos_cxp`, `edw.fact_movimientos_caja`,
  `edw.dim_cliente`, `edw.fact_ventas_detalle`, sus extractores (`etl/extractors/cobros_cxc_extractor.sql`,
  `etl/extractors/pagos_cxp_extractor.sql`, `etl/extractors/movimientos_caja_extractor.sql`),
  transformers (`etl/transformers/fact_transformer.py`) y `PIPELINE_CONFIG` (`etl/orchestrator.py`).
  Validación previa al diseño del módulo propuesto en
  `docs/features/propuesta_nuevos_modulos_roi.md` §2 (Cartera y Flujo de Caja, Gerencia).
- **Método:** `SELECT` puro contra el EDW (`docker exec bi_postgres_edw psql -U etl_user -d edw`)
  y revisión estática de extractores/transformer/orchestrator. **No se ejecutó ninguna escritura
  contra Producción.** H1 y H2 se corrigieron y se recargó `fact_pagos_cxp`/`fact_cobros_cxc` en
  el EDW (Postgres local, Docker) reejecutando el ETL contra SAP en modo solo lectura (`SELECT`);
  el detalle de la corrección aplicada está al final de cada hallazgo.

## Hallazgos

### 🔴 Alta — H1: `fact_pagos_cxp` acumula filas duplicadas en cada corrida del ETL (factor 6.00x)

- **Evidencia:**
  - `etl/extractors/pagos_cxp_extractor.sql` no tiene ningún filtro incremental de fecha (solo
    `WHERE codemp = '{CODEMP}'`), a diferencia de `cobros_cxc_extractor.sql`
    (`WHERE codemp = '{CODEMP}' AND fecemi >= '{FECHA_DESDE}'`) y del resto de extractores
    incrementales del pipeline.
  - `PIPELINE_CONFIG` (`etl/orchestrator.py:281`) registra `fact_pagos_cxp` con
    `'loader': 'fact_inc', 'delta_col': 'fecemi'`: el loader borra solo las filas cuyo `fecha_sk`
    cae en la ventana incremental (`fact_loader.py:33-35`, `DELETE ... WHERE fecha_sk >= dt_start
    AND fecha_sk <= dt_end`) y luego inserta **todo** lo que trajo el extractor — que es la tabla
    completa, sin filtro. Cada corrida borra un rango pequeño y reinserta el histórico entero.
  - **Consultas utilizadas y resultado:**
    ```sql
    SELECT count(*) filas, count(DISTINCT num_transaccion) distintos,
      round(count(*)::numeric/count(DISTINCT num_transaccion),2) as factor_duplicacion
    FROM edw.fact_pagos_cxp;
    -- filas=682732, distintos=113877, factor_duplicacion=6.00

    SELECT tabla_destino, ultimo_etl_ok, registros_carg, estado
    FROM edw.etl_control WHERE tabla_destino='fact_pagos_cxp' ORDER BY fecha_ejecucion;
    -- 6 corridas SUCCESS (2026-07-10 a 2026-07-14), registros_carg creciendo de 113752 a 113877
    -- (crecimiento real del origen), pero el EDW acumula 682732 filas totales (6x)

    SELECT * FROM edw.fact_pagos_cxp WHERE num_transaccion = '00127839' ORDER BY fecha_carga;
    -- 6 filas idénticas (mismo fecha_sk, proveedor_sk, valor_pagado, saldo_pendiente),
    -- una por cada fecha_carga de las 6 corridas registradas en etl_control
    ```
  - El factor de duplicación (6.00) coincide exactamente con el número de corridas `SUCCESS`
    registradas en `edw.etl_control` para esta tabla: confirma que es una duplicación total por
    re-extracción sin filtro, no un problema de grano (no son abonos parciales legítimos).
- **Impacto:** cualquier `SUM(valor_pagado)` o `SUM(saldo_pendiente)` sobre `fact_pagos_cxp` está
  inflado ~6x hoy, y el factor crece con cada corrida futura del ETL. El KPI DPO y cualquier
  "gasto pagado a proveedores" del nuevo módulo saldrían completamente errados si se usa la tabla
  tal cual.
- **Riesgos:** si no se corrige, el módulo de Gerencia mostraría cifras de pagos a proveedores
  varias veces mayores a la realidad — un error que socava la confianza en todo el módulo (y en
  el EDW en general, porque nadie lo había detectado por falta de consumidores de esta tabla).
- **Recomendación:**
  1. **Fix de raíz (ETL):** agregar el token de filtro incremental a `pagos_cxp_extractor.sql`
     (`AND fecemi >= '{FECHA_DESDE}'`, igual que `cobros_cxc_extractor.sql`) para que el
     extractor traiga solo el delta y el DELETE-then-INSERT vuelva a ser idempotente.
  2. **Backfill:** tras el fix, truncar y recargar `fact_pagos_cxp` completo (o deduplicar por
     `num_transaccion` quedándose con la fila de `fecha_carga` más reciente) para eliminar el
     histórico ya duplicado.
  3. **Mientras el fix no se aplique:** el repository del nuevo módulo **no debe** leer
     `fact_pagos_cxp` directamente sin deduplicar; usar
     `DISTINCT ON (num_transaccion) ... ORDER BY num_transaccion, fecha_carga DESC` como mitigación
     temporal, dejando comentado el motivo con referencia a esta auditoría.
  4. Esta corrección es un prerequisito de datos, no parte del alcance del nuevo módulo — tratarla
     como bug fix independiente antes o junto con el desarrollo del backend.
- **✅ Aplicado (2026-07-14):** se agregó `AND fecemi >= '{FECHA_DESDE}'` a
  `pagos_cxp_extractor.sql` (mismo patrón que `cobros_cxc_extractor.sql`). Se truncó
  `edw.fact_pagos_cxp`, se limpió su historial en `edw.etl_control` y se recargó completo
  (`docker compose run --rm etl python orchestrator.py --tablas fact_pagos_cxp`).
  Verificación post-fix: `count(*) = count(DISTINCT num_transaccion) = 113877` (factor de
  duplicación 1.00x). Nota de proceso: la primera corrida usó una imagen Docker desactualizada
  (`docker compose run` no reconstruye automáticamente) — se detectó porque el fix no producía
  efecto observable y se corrigió con `docker compose build etl` antes de la recarga definitiva.
  Se corrió el pipeline completo (`orchestrator.py` sin `--tablas`) después para confirmar cero
  regresiones en las 19 tablas restantes.

### 🔴 Alta — H2: `fact_cobros_cxc.sucursal_sk` es `-1` (desconocido) en el 100% de las filas

- **Evidencia:**
  ```sql
  SELECT count(*) filas, count(*) FILTER (WHERE sucursal_sk = -1) sucursal_desconocido
  FROM edw.fact_cobros_cxc;
  -- filas=212381, sucursal_desconocido=212381 (100%)
  ```
  `cobros_cxc_extractor.sql` no selecciona la columna `establ` (código de sucursal) de
  `cuentasporcobrar`, a diferencia de `pagos_cxp_extractor.sql` que sí la trae (`establ,` en el
  SELECT, comentado como corrección de la auditoría 10) y de `movimientos_caja_extractor.sql`.
  Sin `establ` en el dataframe, `transformar_cobros_cxc` no tiene con qué resolver `sucursal_sk`
  y el loader cae al registro centinela `-1` (comportamiento correcto según regla de negocio 12,
  pero aquí por un dato faltante en el extractor, no por una llave real no encontrada).
- **Impacto:** el módulo propuesto pide explícitamente "DSO ... por sucursal" y "aging ...
  drill-down a cliente" — con `sucursal_sk` siempre `-1`, **no es posible calcular ningún KPI de
  cartera por sucursal** con los datos actuales. Solo es viable a nivel de cliente/empresa global.
- **Riesgos:** si se ignora el hallazgo y se intenta mostrar "DSO por sucursal" igual, todo el
  resultado caería en una única fila "Sucursal desconocida", dando una vista inútil o engañosa.
- **Recomendación:** agregar `establ` a `cobros_cxc_extractor.sql` (mismo patrón ya usado en
  `pagos_cxp_extractor.sql`) y a `transformar_cobros_cxc` para resolver `sucursal_sk` real, luego
  recargar el histórico. **El KPI "DSO por sucursal" del módulo debe marcarse como bloqueado
  hasta este fix**; en la fase 1 el módulo puede lanzarse con DSO/aging a nivel empresa y cliente
  únicamente (que sí es viable hoy), documentando la limitación.
- **✅ Aplicado (2026-07-14):** se agregó `establ` a `cobros_cxc_extractor.sql` y a la lista de
  `normalizar_strings` en `transformar_cobros_cxc` (`etl/transformers/fact_transformer.py`); el
  resolver genérico de llaves (`resolver_llaves_hecho`, `etl/orchestrator.py`) ya sabía resolver
  `sucursal_sk` desde `(codemp, establ)` sin cambios adicionales. Se truncó
  `edw.fact_cobros_cxc`, se limpió su historial en `etl_control` y se recargó completo.
  Verificación post-fix: `sucursal_desconocido = 0` sobre 212,414 filas (antes: 212,381/212,381,
  100%). **El KPI "DSO por sucursal" queda desbloqueado.**

### 🟡 Media — H3: no existe llave documento a documento entre `fact_cobros_cxc` y `fact_ventas_detalle`

- **Evidencia:**
  - `fact_cobros_cxc.num_transaccion` proviene de `cuentasporcobrar.numcpc` (formato numérico,
    ej. `00293367`); `fact_ventas_detalle.num_factura` proviene de `facturas.numfact` (formato
    alfanumérico, ej. `A0129553`, `G0010312`). Los formatos no son comparables.
  - **Consulta de verificación (0 coincidencias):**
    ```sql
    SELECT count(*) FROM edw.fact_cobros_cxc fcc
    WHERE EXISTS (SELECT 1 FROM edw.fact_ventas_detalle fvd
                  WHERE fvd.num_factura = fcc.num_transaccion);
    -- coinciden = 0
    ```
  - Además, `fact_cobros_cxc` no es un log de eventos de cobro (pagos individuales), sino un
    snapshot del documento abierto de `cuentasporcobrar` al momento de la extracción: no hay
    duplicados por `num_transaccion` (212381 filas = 212381 `num_transaccion` distintos), y
    `saldo_documento` puede ser `0` (117915 filas, documento cerrado) o `>0` (94456 filas, saldo
    pendiente) — es el estado del documento, no un movimiento de caja.
- **Impacto:** confirma lo que la propuesta ya anticipaba como riesgo (§2.5): el aging de cartera
  **no puede** hacerse documento a documento contra la factura de venta. Se calcula agregando
  `fact_cobros_cxc` por `cliente_sk` (o por `cliente_sk + num_transaccion` para listar documentos
  abiertos individuales, ya que cada fila SÍ es un documento único aunque no enlace con la
  factura).
- **Riesgos:** ninguno si se documenta la limitación; el riesgo es diseñar el módulo asumiendo
  trazabilidad documento↔factura que no existe.
- **Recomendación:** el aging y el ranking de cobranza priorizada se implementan a nivel
  `(cliente_sk, num_transaccion)` usando `saldo_documento` y `dias_vencimiento`/`fecha_sk` de
  `fact_cobros_cxc` directamente (cada fila ya es un documento de CxC abierto o cerrado), sin
  intentar unir con `fact_ventas_detalle`. Documentar esta regla en
  `docs/auditoria/02_reglas_negocio_validadas.md`.

### 🟡 Media — H4: `dias_vencimiento` es un valor congelado al momento de la extracción, no recalculable

- **Evidencia:**
  - `cobros_cxc_extractor.sql` trae `diasvence AS dias_vencimiento` directo de SAP (ya calculado
    por el ERP a la fecha de extracción); `fecven` (fecha de vencimiento) se extrae pero **no se
    persiste** en `edw.fact_cobros_cxc` — la tabla destino solo tiene `fecha_sk` (mapeado a
    `fecemi`, fecha de emisión, ver `PIPELINE_CONFIG` `delta_col: 'fecemi'`) y `dias_vencimiento`.
  - **Rango observado (evidencia de que el dato es un snapshot, no una regla estable):**
    ```sql
    SELECT min(dias_vencimiento), max(dias_vencimiento), count(*) FILTER (WHERE esta_vencido)
    FROM edw.fact_cobros_cxc;
    -- min=-75, max=15029 (41 años), vencidos=998
    ```
    Valores de `dias_vencimiento` tan grandes (15029) son documentos muy antiguos donde SAP nunca
    actualiza el campo tras el cierre; valores negativos son documentos aún no vencidos al momento
    de la extracción. Como el campo no se recalcula entre corridas del ETL, un documento con
    `dias_vencimiento = 5` extraído hace 3 días en realidad tiene hoy 8 días de vencimiento.
  - Mismo patrón en `fact_pagos_cxp.dias_vencimiento` (rango observado: -888 a 360).
- **Impacto:** si el módulo usa `dias_vencimiento` tal cual para el aging (0-30/31-60/...), el
  bucket mostrado quedará desactualizado por el tiempo transcurrido desde la última corrida del
  ETL (hoy corre manualmente, sin calendarización — ver Observaciones de `CLAUDE.md`).
- **Riesgos:** aging visualmente "congelado" que no coincide con lo que vería un gerente en el
  ERP el mismo día si no se corrió el ETL recientemente.
- **Recomendación:** no usar `dias_vencimiento` como fuente de verdad para el bucket de aging.
  En su lugar, recalcular en el momento de la consulta:
  `dias_vencimiento_actual = CURRENT_DATE - (fecha_emision + dias_credito_cliente)`, usando
  `dim_fecha.fecha_completa` (vía `fecha_sk`) + `dim_cliente.dias_credito` (H5) como aproximación
  de la fecha de vencimiento, ya que `fecha_vencimiento` real no se persiste (ver también H2 del
  extractor). Alternativa de mayor precisión: agregar `fecven` como columna nueva
  (`fecha_vencimiento_sk`) al extractor/transformer/DDL — evaluar costo vs. beneficio antes de
  implementar, dado que la aproximación por `dias_credito` ya cubre el caso de uso del aging.

### 🟢 Informativo — H5: `dim_cliente.dias_credito` está disponible y casi completo, pero es un valor único (30 días) para toda la cartera vigente

- **Evidencia:**
  ```sql
  SELECT count(*) filas_totales, count(*) FILTER (WHERE dias_credito IS NULL) sin_dias_credito,
    round(avg(dias_credito),1) promedio, count(DISTINCT dias_credito) valores_distintos
  FROM edw.dim_cliente WHERE es_vigente = true;
  -- filas_totales=73339, sin_dias_credito=1, promedio=30.0, valores_distintos=1
  ```
- **Impacto:** sirve para el fallback de H4 (aproximar vencimiento), pero **no diferencia clientes
  con distintas condiciones de crédito** (todos tienen 30 días salvo 1 fila nula) — coherente con
  el hallazgo ya documentado en la regla 13 / auditoría 30 (H4: "el ajuste por plazo de crédito
  solo tiene datos reales para 0 y 30 días en el EDW actual"). No es un hallazgo nuevo, se
  confirma vigente para este módulo.
- **Recomendación:** usar `dias_credito` como aproximación aceptable (documentando que hoy es
  homogéneo); no bloquea el módulo.

### 🟢 Informativo — H6: sin multi-moneda; `fact_movimientos_caja.usuario_sk` mayormente sin resolver

- **Evidencia:**
  - No existe ninguna columna de moneda en `fact_cobros_cxc`, `fact_pagos_cxp`,
    `fact_movimientos_caja`, `dim_sucursal` ni en `etl/config/settings.py` (búsqueda
    `moneda|currency|USD|dolar` sin resultados) — confirma operación en una sola moneda, sin
    ajuste necesario para los KPIs DSO/DPO.
  - `fact_movimientos_caja`: `usuario_sk = -1` en 231286/254020 filas (91%);
    `sucursal_sk = -1` en solo 65/254020 (0.03%, aceptable). El campo `usuario_sk` sin resolver no
    bloquea la vista de caja consolidada por sucursal/mes que pide el módulo (§2.2), que no
    depende de usuario.
  - `fact_pagos_cxp.proveedor_sk` y `sucursal_sk` resuelven al 100% (0 filas en `-1`) — a
    diferencia de `fact_cobros_cxc` (H2), CxP sí trae `establ` en el extractor.
- **Impacto:** ninguno sobre el diseño del módulo propuesto.
- **Recomendación:** ninguna acción requerida para este módulo; si en el futuro se necesita
  atribuir movimientos de caja a un cajero/usuario específico, sería un hallazgo aparte.

## Validaciones automáticas (checklist mínimo)

1. **Pérdida de registros:** no evaluado end-to-end contra SAP en esta auditoría (fuera de
   alcance: el foco fue viabilidad del módulo nuevo, no reconciliación completa origen↔EDW de
   estas 3 tablas). Pendiente de validar si se requiere para certificar volúmenes exactos.
2. **Duplicados:** 🔴 encontrados y cuantificados en `fact_pagos_cxp` (H1, factor 6.00x); `fact_cobros_cxc` limpio (0 duplicados por `num_transaccion`).
3. **Cambios inesperados de volumen entre cargas:** confirmado vía `edw.etl_control` que el
   crecimiento de `registros_carg` reportado (113752→113877) es real y modesto, pero el volumen
   final en tabla (682732) no corresponde — causa raíz en H1.
4. **Cambios de granularidad:** grano de `fact_cobros_cxc` y `fact_pagos_cxp` es "documento CxC/CxP
   al momento de extracción" (snapshot), no "evento de cobro/pago" — documentado en H3 y H1;
   importante para no asumir grano de evento al diseñar el repository.
5. **Llaves faltantes/huérfanas:** `fact_cobros_cxc.sucursal_sk` 100% centinela (H2, crítico);
   `fact_cobros_cxc.vendedor_sk` 19993/212381 (9.4%) centinela (no bloquea el módulo, no se usa
   vendedor en los KPIs propuestos); `fact_pagos_cxp` y `fact_movimientos_caja.sucursal_sk`
   prácticamente 100% resueltos (ver H6).
6. **Fechas fuera de rango:** `fact_cobros_cxc` cubre 2013-01-16 a 2026-07-14; `fact_pagos_cxp`
   2016-02-24 a 2026-07-13; `fact_movimientos_caja` 2018-01-02 a 2026-07-14 — todas dentro de
   rango razonable para `dim_fecha`, sin fechas futuras.
7. **Códigos inexistentes:** no se detectaron business keys sin dimensión asociada más allá de los
   centinelas ya reportados en H2/H6.
8. **Integridad referencial / SCD2:** `dim_cliente.dias_credito` verificado consistente
   (H5); no se detectaron múltiples filas vigentes por `hash_anonimo` (constraint único
   `idx_dc_vigente` en `es_vigente=true` lo garantiza a nivel de esquema).

## Resumen de recomendaciones por prioridad

| Prioridad | Hallazgo | Acción | Estado |
|---|---|---|---|
| 🔴 Alta | H1 | Fix del extractor `pagos_cxp_extractor.sql` (agregar filtro incremental) + backfill/dedup de `fact_pagos_cxp` | ✅ Aplicado y verificado (2026-07-14) |
| 🔴 Alta | H2 | Agregar `establ` a `cobros_cxc_extractor.sql` + recarga histórica | ✅ Aplicado y verificado (2026-07-14) |
| 🟡 Media | H3 | Diseñar aging/ranking a nivel `(cliente_sk, num_transaccion)` de `fact_cobros_cxc`, sin join a `fact_ventas_detalle` | Pendiente — decisión de diseño para el backend del módulo |
| 🟡 Media | H4 | Recalcular vencimiento en query (`fecha_emision + dias_credito`), no confiar en `dias_vencimiento` almacenado | Pendiente — decisión de diseño para el backend del módulo |
| 🟢 Info | H5, H6 | Ninguna acción bloqueante | N/A |

**Veredicto de viabilidad para el módulo (actualiza §2.5 de la propuesta):** 🟢 viable en fase 1
**incluyendo el corte por sucursal** — con H1 y H2 corregidos y verificados en el EDW, los datos
de `fact_cobros_cxc` y `fact_pagos_cxp` son confiables (sin duplicación, con sucursal resuelta al
100%). El backend del módulo puede construirse ya sobre datos limpios, aplicando el diseño de H3
(grano documento, sin join a ventas) y H4 (vencimiento recalculado en query, no el campo
congelado).
