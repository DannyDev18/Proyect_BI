# Auditoría 32 — Actualización Módulo Bodega (filtros, valores monetarios, transferencias, reportes)

- **Fecha:** 2026-07-15
- **Alcance:** implementación de `docs/features/plan_actualizacion_modulo_bodega.md`, Fases 1-5 completas
  (incluida la Fase 5 — rediseño de reportes con cambio de contrato coordinado backend+frontend en el mismo
  commit, retomada tras validación inicial de las Fases 1-4). Capas afectadas: backend
  (`backend/app/api/routes/warehouse.py`, `services/warehouse_service.py`, `repositories/warehouse_repository.py`,
  `schemas/warehouse.py`, `core/config.py`) y frontend (`frontend/src/services/bodega.ts`,
  `hooks/bodega.ts`, `pages/DashboardBodega.tsx`, `pages/BodegaAlmacenes.tsx`, `types/bodega.ts`).
  **NO se toca** `etl/`/`edw/` (sin extractores ni DDL nuevo: todo el dato fuente ya está cargado) ni `ml/`.
- **Método:** lectura completa del código real de los 3 archivos backend + 5 archivos frontend del módulo,
  validación con `SELECT` directa contra el EDW real (`bi_postgres_edw`, contenedor vivo) de la hipótesis
  monetaria del plan (D3/RN-B8), y reconciliación posterior (2026-07-15) de esa misma hipótesis directamente
  contra Producción (SAP SQL Anywhere, `xp_plus`/`db_microplus`, host `172.16.50.5:4016`) con `SELECT` de
  solo lectura sobre `kardex` — ver H32-1.

## 1. Punto de partida verificado (código real, no el resumen del plan)

| # | Reclamo del plan | Verificación en código actual |
|---|---|---|
| D1 | Reportes/Excel ignoran `tipo_movimiento`, `fecha_desde`, `fecha_hasta` | **Confirmado, sigue siendo un bug real.** `warehouse.py:344-379` (`GET /reportes/{tipo}` y `/reportes/{tipo}/excel`) y `_generar_reporte` (líneas 331-341) solo reciben/propagan `almacen, categoria, proveedor`. `warehouse_service.py` (`get_reporte_justificacion`, `get_reporte_transferencias`, `get_reporte_analisis_mensual`, líneas 1018-1117) tampoco aceptan los otros 3 filtros. En frontend, `services/bodega.ts:97-118` (`getReporteBodega`, `descargarReporteExcel`) confirma que ni siquiera se envían desde el cliente. |
| D2 | Cobertura desigual de filtros entre gráficos | **Parcialmente desactualizado.** `/rotacion-matriz` (`warehouse.py:146-163`) **ya** acepta y propaga los 6 filtros hasta `WarehouseRepository.get_rotacion_productos` (`warehouse_repository.py:401-464`, incluye `tipo_movimiento` y rango de fechas) — el hallazgo original del plan sobre este endpoint ya no aplica al código actual. `/stock-reorden` y `/necesidad-compra` **excluyen `fecha_desde/hasta` a propósito** tanto en frontend (`bodega.ts:66-74`, se fuerza `fecha_desde: undefined, fecha_hasta: undefined`) como en backend (los endpoints no declaran esos params): es una foto de stock actual, coherente con el propio razonamiento del plan de que ese filtro "no tiene sentido" ahí — se documenta como **N/A intencional**, no como gap a corregir. `queryKeys.ts` ya incluye el objeto `filters` completo en la key de **todos** los hooks de `hooks/bodega.ts` — la teoría "TanStack Query sirve caché vieja por key incompleta" no se sostiene en el código actual. El único gap real que queda es D1 (reportes/Excel). |
| D3 | Falta mostrar dinero condicionado al tipo de movimiento | **Confirmado y con una fuente de datos mejor que la que asumía el plan.** El plan suponía que había que hacer JOIN con `fact_ventas_detalle`/`fact_compras` con riesgo de duplicación por grano. **Hallazgo nuevo (ver §2, H32-1): `edw.fact_movimientos_inventario` ya trae `valor_venta` y `costo_total` a nivel de movimiento** (poblados desde `kardex.totven`/`kardex.costot`, `etl/extractors/kardex_extractor.sql:17-18`), mismo grano que `cantidad_movimiento`. No hace falta ningún JOIN nuevo: basta con sumar esas columnas ya presentes, filtradas por `tipo_movimiento`, en las mismas queries de kardex que ya alimentan `/top-productos` y `/salidas-categoria`. Verificado con `SELECT` real contra el EDW (tabla en H32-1): `FAC` (ventas) trae `valor_venta` poblado (~$28.0M sobre 462.577 filas), `CPA` (compras) trae `costo_total` poblado (~$20.3M sobre 129.595 filas). |
| D4 | Quitar "Estado de Stock vs Punto de Reorden" del dashboard | Confirmado: `DashboardBodega.tsx:350-376` (G5, `useStockReorden`, `soloCriticos`, `stockPagination`). El endpoint `/stock-reorden` se conserva (lo sigue consumiendo `NotificationService`/`WarehouseService.get_notificaciones`, ver auditoría 31). |
| D5 | Mover "Predicción de Necesidad de Compra" a Status Almacén | Confirmado: `DashboardBodega.tsx:381-413` (G6, `useNecesidadCompra`, `compraColumns`). `BodegaAlmacenes.tsx:216-276` ya tiene una sección "§3.3 Plan de compras" propia con horizonte fijo de 45 días, pero renderizada como tabla HTML simple sin paginación real de `recomendados` (usa `{page:1, page_size:50}` fijo) ni columnas de prioridad/justificación como el G6 del dashboard. |
| D6 | Motivo de transferencias sin fundamento estadístico | Confirmado: `_transferencias_completo` (`warehouse_service.py:841-929`) genera `motivo` como string plano con solo 2 datos (días de stock y salida diaria promedio de una ventana de 30 días, vía `get_stock_por_almacen(dias_salidas=30)`). No expone variabilidad, tendencia, venta monetaria del destino, cobertura del origen post-transferencia ni confianza. |
| D7 | Reportes poco intuitivos | Confirmado. `BodegaReportes.tsx` renderizaba el JSON crudo recursivamente y `warehouse_export.py` volcaba el mismo dict a Excel sin formato de negocio. |

## 2. Hallazgos previos a la implementación

| # | Hallazgo | Severidad | Acción |
|---|---|---|---|
| H32-1 | `edw.fact_movimientos_inventario.valor_venta`/`.costo_total` ya están poblados por tipo de movimiento (verificado con `SELECT` real, `bi_postgres_edw`): `FAC` trae `valor_venta` real (venta), `CPA` trae `costo_total` real (costo de compra); el resto de tipos (`TRA`, `DEV`, `EGR`, `ING`, `BOD`, `DEC`) también traen ambas columnas pobladas (heredadas de `kardex.totven`/`costot` para *cualquier* movimiento, no solo venta/compra) pero **no representan una venta ni una compra real** — mostrarlas ahí induciría a error. **Reconciliado 2026-07-15 directamente contra Producción (SAP SQL Anywhere, `xp_plus`/`db_microplus`) con `SELECT` de solo lectura** (`SELECT tiporg, COUNT(*), SUM(totven), SUM(costot) FROM kardex WHERE codemp='01' GROUP BY tiporg`): los 8 tipos coinciden con el EDW dentro de <0.1% (diferencia explicada por el lag normal entre la última corrida del ETL y el estado actual de Producción -- `kardex` en SAP tiene filas hasta `fecha_max=2026-07-15`, es decir datos de hoy mismo, mientras el EDW se cargó en una corrida anterior). Ejemplo exacto: `BOD` -- 7.545 filas en ambos lados, `SUM(totven)=0.00` en ambos, `SUM(costot)≈$789.4k` en ambos. `FAC`: SAP 462.798 filas/$28.02M venta vs EDW 462.577 filas/$28.01M (221 filas de diferencia = ~1 día de ventas nuevas en SAP desde la última carga). Confirma que RN-B8 no está usando una columna con datos espurios o mal poblados -- es el dato real de Producción propagado correctamente por el ETL. | Alta (cambia el diseño de la Fase 2) | RN-B8 se implementa como un mapa cerrado `TIPOS_MOVIMIENTO_CON_MONTO = {"FAC": "venta", "CPA": "compra"}` en `warehouse_repository.py` (junto al catálogo `TIPOS_MOVIMIENTO` ya existente, mismo patrón de catálogo cerrado): solo esos 2 tipos exponen `monto_ventas`/`monto_compra`; el resto expone `None` aunque la columna SQL tenga datos. Se evita el JOIN a `fact_ventas_detalle`/`fact_compras` que proponía el plan (y su riesgo de duplicación por grano) usando directamente las columnas ya presentes en el hecho de kardex. |
| H32-2 | El plan pedía el mapa `TIPOS_MONETARIOS` en `config.py`; el catálogo cerrado equivalente (`TIPOS_MOVIMIENTO`, con sus mismas 8 opciones FAC/TRA/EGR/CPA/DEV/ING/BOD/DEC) ya vive en `warehouse_repository.py`, no en `config.py`. | Baja | Por consistencia con el patrón existente (catálogos cerrados de negocio junto al repositorio que los usa, no en `config.py` que es solo umbrales numéricos parametrizables), `TIPOS_MOVIMIENTO_CON_MONTO` se coloca junto a `TIPOS_MOVIMIENTO` en el mismo archivo. Es una desviación deliberada y menor del plan, documentada aquí. |
| H32-3 | No existe ninguna validación del `tipo_movimiento` recibido contra el catálogo cerrado en ningún endpoint — hoy se concatena directamente como bind param SQL (`_filtros_snapshot`, `warehouse_repository.py:79-98`). No es una inyección SQL (usa bind param), pero un valor fuera de catálogo simplemente no matchea nada y devuelve listas vacías en silencio, sin feedback al usuario. | Media | Se agrega validación centralizada en `WarehouseRepository._filtros_snapshot` (choke point usado por prácticamente todas las queries del módulo): `tipo_movimiento` fuera del catálogo cerrado levanta `ValidationError` (excepción de dominio, capturada por el handler global — regla de capas de `CLAUDE.md`). |
| H32-4 | `_transferencias_completo` usa una ventana de 30 días (`get_stock_por_almacen(dias_salidas=30)` por defecto) para decidir origen/destino; RN-B9 (justificación estadística) necesita una ventana más larga (90 días para CV/tendencia, 180 días para persistencia de la demanda) para no confundir un pico aislado con demanda real. | Media | Se agrega un método de repositorio nuevo y específico para la justificación (`get_series_salidas_producto_almacen`, ventana parametrizable), sin tocar `get_stock_por_almacen` (que sigue siendo la fuente de origen/destino candidatos, sin cambios de contrato). |
| H32-5 (descubierto en verificación post-implementación 2026-07-15) | Los umbrales iniciales de confianza (`CV < 0.5` → alta, `CV < 1.0` → media, valores "de libro" para demanda regular) eran prácticamente inalcanzables para este negocio: verificado contra 200 sugerencias reales del EDW, la mediana real de `coeficiente_variacion_destino` es ≈2.62 (demanda intermitente de repuestos, normal que tenga CV alto) y el mínimo observado fue 0.99 — **199 de 200 sugerencias caían en "baja"**, una señal que no discriminaba nada y por lo tanto no cumplía el propósito de RN-B9 (ayudar a priorizar qué revisar manualmente). | Alta | Umbrales recalibrados contra la distribución real y expuestos como settings (`BODEGA_CV_ALTA=1.2`, `BODEGA_CV_MEDIA=2.5`, `BODEGA_MESES_CONFIANZA_ALTA=5`, `backend/app/core/config.py`); con los mismos 200 datos reales la distribución resultante es 104 baja / 89 media / 7 alta — una señal que sí diferencia. Verificado en vivo contra el EDW tras el cambio. |

## 3. Reglas de negocio nuevas (registradas en `02_reglas_negocio_validadas.md`)

- **RN-B8 (montos condicionados al tipo de movimiento):** los endpoints `/top-productos` y `/salidas-categoria`
  exponen `monto_ventas` (suma de `fact_movimientos_inventario.valor_venta`) solo cuando el filtro
  `tipo_movimiento=FAC`, y `monto_compra` (suma de `.costo_total`) solo cuando `tipo_movimiento=CPA`; en
  cualquier otro caso (sin filtro, u otro tipo del catálogo) el campo es `null` — nunca se infiere venta/costo
  de un movimiento que no es una venta o una compra real, aunque la columna SQL tenga valor heredado del
  kardex genérico (H32-1).
- **RN-B9 (justificación estadística de transferencias):** una sugerencia de transferencia solo se emite si
  `beneficio_neto_estimado > 0` (ahorro por no comprar menos costo logístico estimado,
  `BODEGA_COSTO_LOGISTICO_PCT`) y `meses_con_venta_destino >= BODEGA_MIN_MESES_VENTA` (default 2, ventana de
  6 meses) — nunca se sugiere mover inventario a una bodega sin historial real de venta del artículo. La
  confianza de la sugerencia (`alta`/`media`/`baja`, derivada del coeficiente de variación de la demanda
  diaria del destino y de `meses_con_venta_destino`) se muestra siempre, incluida la confianza baja
  (marcada "revisar manualmente"), nunca oculta en silencio.

## 4. Decisiones de arquitectura confirmadas

1. Fase 2 no hace ningún JOIN nuevo a `fact_ventas_detalle`/`fact_compras`: reutiliza columnas ya presentes
   en `fact_movimientos_inventario` (H32-1), evitando el riesgo de duplicación por grano que el plan
   anticipaba.
2. Fase 4 agrega un método de repositorio nuevo (serie diaria por producto×almacén, ventana configurable)
   en vez de extender `get_stock_por_almacen` — mantiene ese método sin cambios de contrato para los
   consumidores existentes (matriz §3.1, transferencias candidatas).
3. Cambios de esquema (`TransferenciaSugerida`, `ProductoTopSalidas`, `CategoriaSalidas`) son 100% aditivos
   (campos `Optional` nuevos); ningún consumidor existente del contrato se rompe.
4. Fase 5 (rediseño de reportes) **sí cambia el contrato** de `GET /reportes/{tipo}`: `ReporteBodegaResponse`
   pasa de `{generado_en, contenido: dict}` (JSON libre) a `{tipo, titulo, generado_en, filtros_aplicados,
   resumen_ejecutivo: KpiResumenEjecutivo[], interpretacion, secciones: SeccionReporte[]}` (tipado, con
   columnas de negocio declaradas por sección). Es un cambio coordinado backend+frontend en el mismo
   commit (`warehouse_service.py`, `warehouse_export.py`, `schemas/warehouse.py`, `BodegaReportes.tsx`,
   `types/bodega.ts`) — no hay contrato viejo que mantener en paralelo porque el único consumidor
   (`BodegaReportes.tsx`) se actualiza a la vez. El endpoint `GET /reportes/{tipo}/excel` reutiliza el
   mismo contrato tipado (una hoja por sección, formato de moneda/porcentaje, autofiltro y resaltado de
   filas con prioridad "Alta"/"Crítico"), reemplazando el volcado genérico anterior de `_aplanar`.
5. **Criterio de aceptación de D7** ("el usuario debe poder decir qué le dice cada reporte en <30 segundos
   sin explicación", plan §5.4) requiere una sesión de validación con el usuario final del sistema — no es
   automatizable desde este entorno. Se valida aquí lo verificable sin esa sesión: el contrato es correcto
   end-to-end contra el EDW real (ver §5), cada reporte expone `interpretacion` en una frase y KPIs con
   etiqueta de negocio, y las 3 tarjetas del selector nombran explícitamente la pregunta que responden.

## 5. Estado

- [x] Auditoría previa creada antes de modificar código (este documento), incluida validación `SELECT`
      real contra el EDW de H32-1
- [x] Reglas RN-B8/RN-B9 registradas en `docs/auditoria/02_reglas_negocio_validadas.md`
- [x] Fase 1 — filtros E2E en reportes/Excel (`warehouse.py`, `warehouse_service.py`, `services/bodega.ts`)
      + validación cerrada de `tipo_movimiento` (`WarehouseRepository._filtros_snapshot`, H32-3, → 400)
- [x] Fase 2 — montos monetarios condicionados (RN-B8): `monto_ventas` en `/top-productos` y
      `/salidas-categoria`, tooltips en `DashboardBodega.tsx`
- [x] Fase 3 — reorganización del dashboard (D4/D5): tabla de stock vs reorden eliminada de
      `DashboardBodega.tsx`; predicción de necesidad de compra movida a `BodegaAlmacenes.tsx` con
      paginación real (antes `{page:1, page_size:50}` fijo)
- [x] Fase 4 — justificación estadística de transferencias (RN-B9): `WarehouseRepository
      .get_series_salidas_producto_almacen` (batch, sin N+1) + `WarehouseService
      ._justificacion_transferencia`, umbral de emisión, badge de confianza y drawer de detalle en
      `BodegaAlmacenes.tsx`
- [x] Fase 5 — rediseño de reportes: contrato tipado (`ReporteBodegaResponse` con `resumen_ejecutivo`,
      `interpretacion`, `secciones` con columnas de negocio), Excel con hoja Resumen + una hoja por
      sección con formato de moneda/porcentaje/autofiltro/resaltado, y `BodegaReportes.tsx` reescrito
      (tarjetas con la pregunta que responde cada reporte, banda de KPIs, interpretación en lenguaje
      natural, chip-bar de filtros aplicados, tablas con columnas fijas). Verificado end-to-end contra el
      EDW real vía `TestClient` (JSON y Excel descargable con `openpyxl`, ver evidencia en la sesión de
      implementación). Pendiente: sesión de validación con usuario final (criterio de aceptación del plan
      §5.4, no automatizable desde este entorno).

**Validación:** 23 tests de integración nuevos/existentes en verde contra el EDW real
(`backend/tests/integration/test_warehouse_actualizacion_bodega.py` +
`test_warehouse_pagination_prediccion.py`), 136/136 tests unitarios del backend en verde, `tsc --noEmit`
y `oxlint` sin errores en los archivos de frontend tocados, y verificación manual end-to-end del endpoint
Excel (`GET /reportes/{tipo}/excel`) con datos reales del EDW.
