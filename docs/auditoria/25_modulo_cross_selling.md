# Auditoría 25 — Módulo de Venta Cruzada (Cross-Selling)

- **Fecha:** 2026-07-13
- **Alcance:** implementación del módulo descrito en `docs/features/modulo_cross_selling_requerimientos.md` (plan en `docs/features/plan_modulo_cross_selling.md`). Capas afectadas: ML (`ml/`), backend (`backend/app/`), frontend (`frontend/src/`). **NO se modifica** `etl/` (sin extractores/transformers nuevos: el dato ya está en `fact_ventas_detalle`).
- **Método:** lectura del contrato existente (`ml/contracts/models/recommendation.json` v0.1.0), del motor actual (`ml/src/training/train_recommendation_engine.py`, `ml/src/data/make_dataset.py::fetch_market_basket`), del serving (`backend/app/ml/model_loader.py`, `inference.py`, `prediction_service.py`) y validaciones **SOLO SELECT** contra el EDW vivo (`postgres_edw`, esquema `edw`).

## 0. Mapeo origen → EDW (Fase 0 del requerimiento)

El requerimiento pedía auditar `renglonesfacturas`/`encabezadofacturas`/`kardex`/`articulos` en SAP. Se descarta: el EDW ya es la fuente oficial (CLAUDE.md) y contiene el mapeo completo:

| Origen SAP (solo referencia histórica) | EDW (fuente real usada) |
|---|---|
| `renglonesfacturas` (codart, cantidad, precio) | `edw.fact_ventas_detalle` (grano línea de venta) |
| `encabezadofacturas` (num_factura, codcli, fecfac) | `fact_ventas_detalle.num_factura` + `dim_fecha` + `dim_cliente` |
| `articulos` (codart, nombre, codgrupo, precio, ultcos) | `edw.dim_producto` (SCD2): `codart`, `nombre_articulo`, `clase`/`subclase` (equivalen a `codgrupo`), `precio_oficial`, `costo_promedio` |
| `kardex` | no aplica a este módulo (es demanda/inventario, ya cubierto por `demand_rf`) |

Flujo de la aplicación / punto de integración: el vendedor (rol `ventas`) opera en `DashboardVentas.tsx`, que conserva la tarjeta de recomendaciones por cliente existente (`GET /analytics/ventas/recommendations`). El **Asistente de Venta Cruzada** (canasta simulada) es un módulo nuevo con página propia — `/ventas/cross-selling` (`VentasCrossSelling.tsx`), mismo patrón que "Metas y Comisiones" (`/ventas/metas`) — no una sección embebida en el dashboard general; no es un carrito transaccional (el ERP SAP sigue siendo el único sistema que factura).

## 1. Validaciones ejecutadas contra el EDW (SOLO SELECT, 2026-07-13)

Ventana de datos vigente: `fact_ventas_detalle` cubre 2018-01-02 a 2026-07-13. "Último trimestre" = `>= 2026-04-13`.

| Validación | Resultado |
|---|---|
| Facturas válidas totales (estado <> anulado) | 235.276 |
| Facturas con 2+ productos distintos (universo de canastas útiles) | 104.929 (44,6%) |
| `codart` únicos con venta válida | 6.340 |
| Reglas activas en `recommendation.pkl` v0.1.0 | 494 (247 pares × 2 direcciones) |
| `codart` únicos que aparecen como antecedente (`item_A`) en v0.1.0 | 78 |
| Facturas del último trimestre con 2+ productos | 4.264 |
| **Cobertura v0.1.0** (≥1 sugerencia posible, ≥1 producto de la canasta con regla) | **3.749 / 4.264 = 87,9%** — línea base a superar en Fase 3 |
| `dim_producto` vigente (`es_vigente`, sin centinela `-1`) | 8.146 filas |
| Con `precio_oficial` > 0 | 8.144 / 8.146 (99,98%) |
| Con `costo_promedio` > 0 | 7.506 / 8.146 (92,1%) |
| Categorías (`clase`) distintas vigentes | 22 |

**Conclusión de datos:** margen es derivable de forma confiable para ~92% del catálogo vigente vía `precio_oficial − costo_promedio` (`dim_producto`); el 8% restante sin costo usa fallback (ordenar solo por lift, sin factor margen — documentado, no se inventa un costo). La cobertura base (87,9%) es más alta de lo esperado con solo 78 productos con regla — son los de mayor rotación — pero el 12,1% de canastas sin sugerencia justifica el fallback por categoría (§2.1 del plan) y motiva revisar `min_support` en el re-análisis de Fase 3.

## 2. Hallazgos previos a la implementación

| # | Hallazgo | Severidad | Acción |
|---|---|---|---|
| H25-1 | El requerimiento pide extraer de SAP (`renglonesfacturas` etc.) y guardar el dataset como CSV. | Baja | Se usa el EDW exclusivamente (ya validado arriba) y dataset efímero en memoria (patrón `fetch_*` existente), sin CSVs versionados. |
| H25-2 | El requerimiento pide un endpoint suelto `POST /recomendar_productos` en `main.py` con motor que carga el `.pkl` por su cuenta. | Media | Se reutiliza `ModelLoader` singleton (clave `association`, ya cargado en el lifespan) + capas routes→services→repositories bajo `/analytics/ventas/cross-selling/*`. |
| H25-3 | El contrato v0.1.0 no tiene `lift`/`confidence` mínimos ni fallback: 12,1% de canastas del último trimestre quedarían sin sugerencia. | Media | Fallback por categoría/popularidad (§2.4 del plan); umbrales `CROSS_SELL_MIN_LIFT` configurables. |
| H25-4 | `costo_promedio` nulo en 7,9% de productos vigentes → margen no derivable para ese subconjunto. | Baja | La heurística de margen se omite (no se sustituye por un valor inventado) cuando `costo_promedio` es NULL o 0; se ordena solo por lift para esos productos, documentado en el contrato v0.2.0. |
| H25-5 | El requerimiento pide instalar `surprise` para filtrado colaborativo. | Baja | Descartado (dependencia pesada sin mantenimiento activo); el candidato item-item se implementa con `scikit-learn` (cosine similarity), ya presente en `ml/requirements.txt`. |
| H25-6 | No existe tabla de telemetría de aceptación/rechazo de sugerencias. | Media | Tabla nueva `public.recomendaciones_eventos` (DDL en `edw/07_public_app_tables.sql` + modelo SQLAlchemy, patrón de `metas_comerciales_operativas`). |

## 3. Regla de negocio nueva (a registrar en `02_reglas_negocio_validadas.md`)

- **RN-CS1 (formato de sugerencia):** Top-N configurable (`CROSS_SELL_TOP_N`, default 5); cada sugerencia expone `codart`, `nombre`, `precio` (`precio_oficial` vigente), `categoria` (`clase`), `score` (lift o score combinado del ganador de backtest) y `motivo` textual ("Los clientes que llevan X suelen llevar Y" para reglas de asociación; "Popular en esta categoría" para el fallback). Se excluyen productos ya presentes en la canasta simulada y, si hay `cliente_id`, los ya comprados por ese cliente en el histórico. Fallback por categoría cuando ningún producto de la canasta tiene regla con score ≥ `CROSS_SELL_MIN_LIFT`.
- **RN-CS2 (telemetría):** cada sugerencia mostrada genera un evento `mostrada` en `public.recomendaciones_eventos`; el clic en "Agregar" genera `aceptada`. La tasa de conversión = `aceptadas / mostradas` en la ventana consultada.

## 4. Decisiones de arquitectura

1. **Sin ETL/DDL nuevo en `edw.*`** — el dato de ventas y catálogo ya está cargado; el ETL roto (`etl/loaders/` borrado, riesgo abierto de CLAUDE.md) no bloquea este módulo.
2. **Modelo re-analizado, no descartado a priori** (decisión del usuario, alta prioridad): se compite co-ocurrencia re-tuneada vs Apriori/FP-Growth (`mlxtend`, solo en `ml/requirements.txt`) vs item-item (`scikit-learn`) vs híbrido, con selección por backtest temporal (Precision@K/Recall@K/Hit-Rate/cobertura) — detalle en §2.3 del plan. Contrato-primero: v0.2.0 en `draft` antes de entrenar.
3. **Capas backend:** `catalog`/`recomendaciones` repositorios (SQL) → `prediction_service.get_basket_recommendations` (heurísticas + fallback) + `recommendation_event_service` (telemetría) → `routes/sales.py` bajo `/analytics/ventas/cross-selling/*`, RBAC `vendedor_checker` (KPIs también accesibles a `gerencia`).
4. **Sin dependencia nueva en el backend** salvo que gane el híbrido/colaborativo (H-20): el diseño prioriza artefactos-DataFrame precomputados para que el runtime del backend no cambie.

## 5. Estado

- [x] Auditoría previa creada antes de modificar código
- [x] Validaciones SELECT ejecutadas contra el EDW vivo (§1)
- [x] EDA + grid experimental + contrato v0.2.0 draft (Fase 2) — `ml/notebooks/eda_cross_selling.py`
- [x] Backtest y selección del modelo ganador (Fase 3) — ganador: filtrado colaborativo
      item-item (similitud coseno, ventana 2 años), Precision@5=0.077, cobertura=97.9% (vs
      línea base 87.9%). Detalle completo y las 31 combinaciones evaluadas en
      `ml/REPORTE_MEJORA_MODELOS.md` §"Módulo Venta Cruzada". Contrato v0.2.0 `active`,
      `contract_validator` 6/6 OK. Nota: el agente inicial asignado a esta fase falló por
      límite de sesión tras dejar el diseño (EDA, arnés de backtest, motor multi-estrategia)
      completo pero sin ejecutar; se retomó y se ejecutó el backtest + publicación
      directamente en esta sesión.
- [x] Implementación frontend (Fase 5) — Sale Assistant, SuggestionCard, CrossSellKpiPanel
      en página propia `VentasCrossSelling.tsx` (`/ventas/cross-selling`, nav propio en el
      Sidebar), mismo patrón que Metas y Comisiones -- no embebido en `DashboardVentas.tsx`
      (corrección pedida por el usuario tras la primera entrega, ver nota abajo). Groundwork
      backend (tabla telemetría, modelo ORM, config, catalog_repository, schemas) completo.
- [x] Implementación backend final (Fase 4) — `inference.get_basket_recommendations`,
      `PredictionService.get_basket_recommendations/log_recommendation_event/get_conversion_kpis`,
      endpoints en `routes/sales.py`, wiring en `dependencies.py`. Verificado end-to-end
      contra el backend real (§6), incluyendo 2 bugs reales encontrados y corregidos.
- [x] KPIs + documentación + cierre (Fase 6) — `CrossSellKpiPanel` visible en la página
      propia `/ventas/cross-selling` (accesible también a gerencia/administrador vía
      `vendedor_checker`); CLAUDE.md, `02_reglas_negocio_validadas.md` y
      `ml/REPORTE_MEJORA_MODELOS.md` actualizados; guía del vendedor en §8 de este documento.

**Nota sobre el orden de ejecución real:** por restricciones prácticas de la sesión, el
frontend (Fase 5) y el groundwork de backend se adelantaron en paralelo a la Fase 3 (todo lo
que no dependía del esquema final del modelo ganador); el cableado final del backend se cierra
después de conocer el ganador, como exige la dependencia real del plan (§4).

## 6. Verificación end-to-end (2026-07-13)

Backend levantado en Docker (`bi_backend`) con el `.pkl` reentrenado, login real con un
usuario `ventas` semilla y llamadas HTTP directas a los 5 endpoints nuevos + el endpoint
legado por-cliente:

- `GET /cross-selling/productos?q=cable` → autocompletar OK.
- `POST /cross-selling/sugerencias` → **bug real encontrado y corregido**: `CROSS_SELL_MIN_LIFT=1.5`
  se diseñó pensando en reglas de asociación (`lift` > 1), pero el ganador del backtest
  (item-item) expone similitud coseno en `[0,1]` — el umbral rechazaba SIEMPRE todas las
  filas y el endpoint caía permanentemente al fallback de popularidad. Corregido en
  `prediction_service.py` (`_FUENTES_ESCALA_LIFT`): el umbral solo aplica a fuentes en
  escala de lift; item-item se sirve por ranking de `score` sin ese filtro. RN-CS1
  actualizada en `02_reglas_negocio_validadas.md` §17.
- Segundo bug encontrado y corregido: `get_top_producto_categoria` comparaba
  `text[] = varchar[]` en SQL crudo (`ARRAY[]::varchar[]` vs el parámetro bindeado como
  `text[]` por psycopg2) — Postgres no tiene ese operador. Simplificado a
  `NOT (codart = ANY(:excluir))`, que ya maneja el caso de lista vacía sin la comparación
  explícita.
- `POST /cross-selling/eventos` (mostrada + aceptada) → registros creados en
  `public.recomendaciones_eventos`.
- `GET /cross-selling/kpis` → tasa de conversión calculada correctamente (100% con 1
  mostrada / 1 aceptada en la prueba); datos de prueba limpiados después.
- `GET /analytics/ventas/recommendations?cliente_id=...` (endpoint legado) → sigue
  funcionando, ahora leyendo `score` en vez de `lift`.
- Backend: `python -m py_compile` limpio en los 10 archivos nuevos/modificados; import
  completo de `app.main:app` sin errores.
- ML: `contract_validator` 6/6 contratos OK; artefacto publicado y verificado.
- Frontend: `tsc -b` sobre el proyecto completo reporta 1 error preexistente en
  `components/ui/Select.tsx` (no relacionado a este módulo, viene del trabajo previo de
  Bodega ya bundleado en el historial de git); ningún archivo de `crossSelling/` genera
  error de tipos.

## 6.1 Correcciones tras feedback de uso real (2026-07-13, misma sesión)

Tres pedidos del usuario tras probar la primera entrega, cada uno con hallazgos reales:

1. **Módulo propio, no embebido:** "Venta Cruzada" pasó a página propia
   `/ventas/cross-selling` (`VentasCrossSelling.tsx`), mismo patrón que Metas y
   Comisiones -- se sacó de `DashboardVentas.tsx`. Nav propio en el Sidebar.
2. **Búsqueda en vivo (autocompletar mientras se escribe):** se creó
   `components/ui/Autocomplete.tsx` (genérico, con debounce de 250ms vía
   `hooks/useDebouncedValue.ts`) reemplazando el patrón de submit-por-Enter de
   `SearchInput` tanto para el buscador de producto como para el de cliente.
3. **Búsqueda de cliente por cédula/RUC o nombre:** nuevo endpoint
   `GET /cross-selling/clientes?q=`. Estos campos (`id_cliente_transaccional`,
   `nombre_cliente`) son PII real y viven SOLO en `public.cliente_lookup` -- tabla
   aislada del EDW a propósito (regla de negocio 8, CLAUDE.md); `edw.dim_cliente` solo
   tiene el hash. La búsqueda corre contra `cliente_lookup`, nunca contra columnas
   hasheadas del EDW.
4. **Diversidad entre categorías (hallazgo real, no solo una preferencia de UI):** se
   verificó que para ciertos productos (ej. baterías, codart `604232`) los 20 vecinos
   entrenados por el artefacto item-item son TODOS de la misma categoría (`BAT`) --
   confirmado inspeccionando el `.pkl` directamente (`item_A='604232'` → 20/20 filas
   con `categoria='BAT'`). El tope por categoría (`CROSS_SELL_MAX_POR_CATEGORIA`) no
   alcanza cuando el pool completo carece de diversidad. Se agregó **RN-CS3**:
   inyección activa de hasta 2 productos de OTRAS categorías (mejor vendido de cada
   categoría, `catalog_repository.get_top_productos_diversos`) cuando la selección
   final queda concentrada en una sola categoría. **Bug encontrado durante esta misma
   corrección:** la primera versión de `get_top_productos_diversos` devolvió
   `Z-999 / "BATERIAS CHATARRAS"` ($0.735) como sugerencia -- una categoría-cajón con 1
   solo producto vigente. Corregido excluyendo categorías con `clase` vacía/nula o con
   menos de `min_productos_categoria` (default 5) artículos vigentes.
5. Verificado de nuevo end-to-end contra el backend real tras cada corrección: cliente
   buscable por nombre parcial ("a" → 10 resultados), sugerencias para `604232` ahora
   incluyen `REP`/`SON` en vez de solo `BAT` o chatarra, y un producto ya diverso
   (`ANTI 557-012`) no se ve alterado por la inyección (la diversidad natural del
   item-item se respeta, la inyección solo actúa cuando hace falta).

## 6.2 Segunda ronda de correcciones (2026-07-13, feedback tras primer uso en el navegador)

1. **`search_clientes` debía anclarse en el EDW, no solo en `public.cliente_lookup`:**
   la primera versión consultaba `cliente_lookup` directamente sin pasar por
   `edw.dim_cliente`. Corregido: la query ahora ancla en `edw.dim_cliente` (filtra
   `es_vigente` SCD2 y excluye el centinela `cliente_sk = -1`, regla 12 CLAUDE.md,
   igual que `get_cliente_sk_vigente`) y hace `JOIN` a `public.cliente_lookup` solo para
   los dos campos que por diseño de anonimización (regla de negocio 8) no pueden vivir
   en el EDW: `id_cliente_transaccional` y `nombre_cliente`. El EDW queda como fuente
   real que gobierna qué clientes son buscables (vigentes, no el centinela).
2. **Dropdown de autocompletar solo mostraba ~1 elemento (ambos buscadores):** causa
   raíz de stacking/clipping en CSS, no un bug de datos. El buscador de producto vive
   dentro de un `ChartCard`, cuyo contenedor de children tiene `overflow-hidden`
   incondicional -- con `height="h-auto"` el box se ajusta al contenido visible y
   recorta cualquier `position: absolute` que se salga de esa caja. El buscador de
   cliente, aunque no está dentro de un `ChartCard`, se pintaba por DEBAJO del
   `ChartCard` del asistente inmediatamente siguiente: ambas tarjetas usan animaciones
   de entrada (`animate-fade-in-up`/`animate-fade-in`) que crean su propio *stacking
   context*; `z-index` solo compara elementos DENTRO del mismo stacking context, así
   que subir el z-index del dropdown no alcanza para pintarlo sobre un hermano
   posterior con su propio stacking context. **Corregido de raíz**: el dropdown de
   `Autocomplete.tsx` ahora se renderiza vía `createPortal` a `document.body` con
   `position: fixed`, calculando sus coordenadas desde `getBoundingClientRect()` del
   input real (recalculadas en scroll/resize) -- así queda completamente fuera de
   cualquier `overflow-hidden` o stacking context ancestro, para los dos buscadores.

## 6.3 Corrección de KPIs poco accionables para el vendedor (2026-07-13, feedback de uso real)

**Hallazgo del usuario:** el panel de KPIs en `/ventas/cross-selling` (`CrossSellKpiPanel`)
solo mostraba telemetría histórica acumulada (`sugerencias_mostradas`/`aceptadas`/
`tasa_conversion_pct`, RN-CS2) — en un módulo recién lanzado esos contadores parten en
cero y no ayudan al vendedor a cerrar la venta que tiene enfrente; además el panel se
mostraba primero, antes del propio asistente.

**Corrección:**

1. **Resumen de la canasta en tiempo real** (`SaleAssistant.tsx`): tres KPIs calculados
   en el cliente a partir del estado de la canasta simulada — Nº de productos, Valor
   total (suma de `precio`) y Margen Estimado (suma de `margen_unitario`, con aviso
   cuando algún producto no tiene costo derivable, H25-4). Es la información que
   realmente sirve mientras se arma la venta.
2. **`margen_unitario` expuesto en el contrato** (antes se calculaba en
   `prediction_service.py` solo para reordenar internamente y se descartaba, H25-1 del
   código): agregado a `SugerenciaProducto` y `ProductoBusqueda`
   (`schemas/cross_selling.py`), calculado también en
   `CatalogRepository.search_productos` (antes solo en `get_products_info`) para que
   los productos agregados por búsqueda directa (no solo por sugerencia) también
   aporten margen al resumen de la canasta. `SuggestionCard` ahora muestra el margen
   unitario de cada sugerencia (`+$X margen`) cuando es derivable.
3. **`CrossSellKpiPanel` reubicado como sección secundaria** ("Impacto histórico del
   asistente"), debajo del asistente en vez de arriba, con un estado vacío explícito en
   vez de mostrar 0/0/0% sin contexto cuando `sugerencias_mostradas == 0`.

No hay cambio de esquema en `edw.*` ni en `public.recomendaciones_eventos`: el margen ya
era derivable de `dim_producto.precio_oficial`/`costo_promedio` (§1), solo faltaba
exponerse en el contrato de respuesta.

## 6.4 KPIs reemplazados por "Top combinaciones de productos" (2026-07-13, segundo feedback)

**Feedback del usuario tras §6.3:** las 3 KpiCards de resumen de canasta (productos,
valor, margen) que se agregaron en §6.3 se quitan -- el usuario pidió, en cambio, que
el panel de KPIs vuelva a estar arriba de la página (como en el diseño original) pero
con información realmente relevante, no telemetría vacía. Se le preguntó qué tipo de
dato prefería (tasa histórica de venta cruzada, ticket promedio con/sin cross-sell, top
combinación de productos, o la conversión del asistente) y eligió **top combinación de
productos**.

**Implementación:**

1. **Nuevo KPI "Top combinaciones de productos"**: 3 tarjetas con las parejas de
   productos con mayor co-ocurrencia histórica en facturas válidas de los últimos 2 años
   (`CROSS_SELL_TOP_COMBINACIONES_DIAS`, mismo horizonte que el modelo item-item
   ganador). Se calcula con un self-join de `edw.fact_ventas_detalle` sobre
   `num_factura` (`CatalogRepository.get_top_combinaciones`), nuevo endpoint
   `GET /cross-selling/top-combinaciones` (`TopCombinacionesResponse`), consumido por
   `TopCombinacionesPanel.tsx`. A diferencia de la telemetría del asistente (RN-CS2),
   este KPI **siempre tiene datos** porque se calcula directo sobre el histórico de
   ventas real, no sobre el uso acumulado del asistente -- resuelve el problema
   original (KPIs en cero para un módulo recién lanzado) con un ejemplo concreto y ya
   validado de qué ofrecer junto a qué.
2. **Reposicionado arriba de la página** (`VentasCrossSelling.tsx`), antes del selector
   de cliente y del asistente -- como pidió el usuario.
3. **`CrossSellKpiPanel` (telemetría de conversión, RN-CS2) queda sin usar en esta
   página** pero se conserva el componente y el endpoint `/cross-selling/kpis`
   intactos: el usuario no eligió mostrar esa telemetría aquí, pero sigue siendo el
   mecanismo de medición de RN-CS2 y el comentario original ("reutilizable en Ventas y
   Gerencia") sigue siendo válido para una futura vista de Gerencia.
4. Las 3 KpiCards de resumen de canasta de §6.3 (productos/valor/margen) se removieron
   de `SaleAssistant.tsx`; `margen_unitario` se mantiene en el contrato de
   `SugerenciaProducto`/`ProductoBusqueda` y en `SuggestionCard` (línea "+$X margen" por
   sugerencia), ya que no fue parte de lo que el usuario pidió quitar.

## 7. Estado final

- [x] Todas las fases (1-5) completas y verificadas contra el EDW/backend/frontend reales.
- [ ] Fase 6 (KPIs en Gerencia, guía del vendedor extendida, cierre formal) — ver abajo.

## 8. Guía breve del vendedor — Asistente de Venta Cruzada

1. En el Dashboard de Ventas, busca un cliente (opcional) para personalizar las
   sugerencias con lo que ese cliente ya compró antes (no se le repetirá lo que ya lleva).
2. En la sección "Venta Cruzada", usa el buscador para agregar productos a la canasta
   simulada (por código SAP o por nombre).
3. Las sugerencias aparecen automáticamente: nombre, precio, categoría y el motivo
   ("Clientes con productos similares en su canasta también compraron este producto" o
   "Popular en esta categoría" cuando no hay una coincidencia fuerte).
4. Clic en "Agregar" para sumar la sugerencia a la canasta (también dispara el registro de
   aceptación) y ver nuevas sugerencias basadas en la canasta ampliada.
5. La canasta es una simulación de apoyo — la venta real se sigue facturando en SAP; este
   asistente no reemplaza al ERP.
6. El panel de KPIs arriba del asistente muestra cuántas sugerencias se han mostrado,
   cuántas se aceptaron y la tasa de conversión resultante.
