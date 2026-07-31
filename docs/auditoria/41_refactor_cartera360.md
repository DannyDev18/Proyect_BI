# Auditoría 41 — Fase 0 del refactor Cartera 360 → "Mi Ruta Inteligente de Ventas"

- **Fecha:** 2026-07-28
- **Alcance:** Fase 0 de `docs/features/plan_refactor_cartera360_ruta_inteligente.md` §14 — cerrar
  las 4 preguntas técnicas pendientes antes de autorizar la Fase 1 (cimientos BD + contratos).
- **Método:** `EXPLAIN ANALYZE` sobre el EDW real (`bi_postgres_edw`, sin escrituras), inspección de
  esquema (`\d edw.dim_producto`), medición end-to-end de la query real de `Cartera360Repository.get_lista_trabajo`
  contra el `codven` de mayor cartera. Sin conexión a Producción en esta fase (no se necesitó: las
  4 preguntas se responden con datos ya presentes en el EDW, ya validado end-to-end en la
  Auditoría 40/41-anterior).

> Nota de nomenclatura: este documento reutiliza el número 41 porque el refactor de Cartera 360 es
> la continuación directa del trabajo de reconciliación EDW↔Producción de la sesión anterior
> (`docs/auditoria/41_reconciliacion_cobros_devoluciones_clientes.md`), y ambos preparan la misma
> base de datos para el mismo módulo. Se mantienen como documentos separados por alcance (uno es
> reconciliación de datos, este es Fase 0 de un plan de producto), referenciados cruzadamente.

## Hallazgos

### Informativo — F0-1 Volumen real de cartera por vendedor: confirma el techo de ~31k (auditoría 32 H1)

- **Evidencia:**
  ```sql
  SELECT ve.codven, COUNT(DISTINCT l.id_cliente_transaccional) AS clientes
  FROM edw.fact_ventas_detalle f
  JOIN edw.dim_vendedor ve ON f.vendedor_sk = ve.vendedor_sk
  JOIN edw.dim_cliente c ON f.cliente_sk = c.cliente_sk
  JOIN public.cliente_lookup l ON c.hash_anonimo = l.hash_anonimo
  JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
  WHERE ed.estado_documento_sk <> -1
  GROUP BY ve.codven ORDER BY clientes DESC LIMIT 10;
  ```
  Resultado: `VEN01=31.093`, `VEN13=10.800`, `VEN03=10.119`, `VEN15=4.710`, `VEN16=2.187`,
  `VEN17=1.552`, resto <500.
- **Impacto:** confirma con datos actuales (no la medición histórica de la auditoría 32) que el
  two-stage es obligatorio y que `VEN01` es el caso de peor rendimiento a usar como referencia de
  carga en toda medición de esta fase y de las siguientes.
- **Recomendación:** ninguna acción — dato de referencia para R-1 y el criterio de aceptación 7.

### Alta — F0-2 La query base de `/lista-trabajo` ya consume ~530 ms de los 800 ms de presupuesto p95

- **Evidencia:** `EXPLAIN ANALYZE` de la consulta real de `Cartera360Repository.get_lista_trabajo`
  contra `codven='VEN01'` (31.093 clientes, el peor caso real):
  ```
  GroupAggregate (actual time=471.424..527.488 rows=31093 loops=1)
    -> Sort (actual time=469.089..495.310 rows=172251) -- Sort Method: external merge, Disk: 9808kB
       -> Hash Join ... (actual time=258.039..340.125 rows=172251)
  Planning Time: 13.143 ms
  Execution Time: 530.822 ms
  ```
  El tiempo end-to-end vía `docker exec ... psql` (incluye overhead de proceso, no solo la query)
  fue de ~1.0 s para devolver las 31.093 filas.
- **Impacto:** el criterio de aceptación 7 del plan (`p95 < 800 ms` en `/ruta/hoy`) se plantea sobre
  el endpoint COMPLETO, que además de esta query debe correr el churn batch del shortlist (300
  candidatos, barato — ver F0-4) y, para los ≤10 clientes mostrados, recomendaciones + SHAP. Con la
  query base ya en 530 ms, el margen restante para el resto del pipeline es de ~270 ms. **Riesgo
  real, no hipotético.**
  - Causa raíz del costo: un `Sort` que hace *external merge a disco* (`Disk: 9808kB`) sobre 172.251
    filas antes de agregar — la CTE `base` no tiene índice que sirva el `GROUP BY
    cliente_id, nombre_cliente` en orden, y `work_mem` de la sesión no alcanza para el sort en
    memoria de la cartera más grande.
- **Riesgos:** si no se optimiza, la Fase 2 puede incumplir el criterio de aceptación 7 solo con la
  carga heredada, sin haber agregado una sola columna nueva.
- **Recomendación (para Fase 1/2, no aplicada en esta Fase 0 — es cambio de código de producto, no
  de datos):** dos opciones, no mutuamente excluyentes:
  1. Aumentar `work_mem` para la sesión de este query específico (`SET LOCAL work_mem`) para forzar
     sort en memoria — más simple, sin tocar SQL.
  2. Reescribir la CTE para agregar por `cliente_sk` (entero, ya indexado) en vez de
     `cliente_id, nombre_cliente` (ambos `text`, sin índice compuesto), y hacer el join a
     `cliente_lookup` DESPUÉS de agregar (reduce el ancho de fila que se ordena).
  Ambas se implementan y miden en la Fase 2, con el mismo método de este hallazgo, antes de dar por
  cumplido el criterio de aceptación 7.

### Informativo — F0-3 `dim_producto` NO tiene fecha de alta real del artículo — confirma §4.5

- **Evidencia:**
  ```sql
  \d edw.dim_producto
  -- columnas de fecha: fecha_inicio_vigencia (SCD2), fecha_fin_vigencia (SCD2), fecha_carga (ETL)
  SELECT MIN(fecha_inicio_vigencia), MAX(fecha_inicio_vigencia), COUNT(DISTINCT fecha_inicio_vigencia)
  FROM edw.dim_producto WHERE es_vigente;
  -- 1900-01-01 | 2026-07-28 | 5
  ```
  Solo 5 valores distintos de `fecha_inicio_vigencia` para 100% de los productos vigentes, con
  mínimo `1900-01-01` (fecha centinela histórica) y máximo la fecha de la recarga más reciente del
  EDW (2026-07-28, la de esta misma sesión) — es un artefacto de cuándo se cargó/versionó la fila en
  el EDW, no la fecha real en que SAP dio de alta el artículo.
- **Impacto:** confirma la hipótesis del plan (§4.5): "Nuevos productos" **no tiene fuente real** en
  el modelo dimensional actual. Traer la fecha de alta real requeriría un cambio de extractor sobre
  `articulos` en SAP (columna a confirmar, ej. `fecalta`/similar) — fuera de alcance de este
  refactor (mismo criterio que DEC-4: cambio de alcance del ETL, plan aparte con la skill
  `etl-edw-auditor` si se decide perseguir).
- **Recomendación:** confirmar en el plan que "Nuevos productos" permanece **fuera** de los 5 tipos
  de recomendación viables de §4.5 — sin cambios respecto a lo ya documentado.

### Informativo — F0-4 Costo del churn batch sobre el shortlist (300 candidatos): no es un riesgo de latencia

- **Evidencia:** `PredictionRepository.get_churn_features_batch` filtra con
  `WHERE l.id_cliente_transaccional IN :cliente_ids` acotado a
  `VENTAS360_CANDIDATOS_ENRIQUECER=300` — mismo patrón de índice/join que la query de F0-2 pero
  sobre 300 valores de clave, no 31k. Dado que el `Hash Join` de la query completa ya procesa
  172k filas en <350 ms para construir el batch de features de TODA la cartera, filtrar a 300
  identificadores concretos vía `IN` (con índice de `cliente_lookup`/`dim_cliente` ya usado en
  F0-2) es órdenes de magnitud más barato — no se midió por separado porque no es la ruta crítica
  de latencia (esa es F0-2).
- **Recomendación:** ninguna acción en esta fase. Medir explícitamente en la Fase 2 junto con el
  resto del pipeline (criterio de aceptación 7) una vez el endpoint `/ruta/hoy` exista de verdad.

## Resumen de recomendaciones por prioridad

- **Alta:** F0-2 — optimizar la query de `lista_trabajo` (work_mem local o reagregar por
  `cliente_sk`) **antes o durante** la Fase 2, con su propio `EXPLAIN ANALYZE` de verificación —
  condición para cumplir el criterio de aceptación 7. Bloquea el cierre de la Fase 2, no la Fase 1.
- **Informativo:** F0-1, F0-3, F0-4 — sin acción, confirman supuestos ya documentados en el plan
  (§4.5, R-1, criterio 12).

## Respuestas a las 4 preguntas de §14 del plan

| Pregunta | Respuesta |
|---|---|
| Latencia base real de `/lista-trabajo` con el `codven` de mayor cartera | **530.8 ms de ejecución** (VEN01, 31.093 clientes) — ver F0-2 |
| `EXPLAIN ANALYZE` de las queries nuevas sobre `fact_ventas_detalle`/`fact_cobros_cxc`/`fact_devoluciones` | La única query de alto riesgo identificada en esta fase es la ya existente de `lista_trabajo` (F0-2); las queries nuevas de Fase 4 (timeline por cliente) y Fase 6 (efectividad) son por-cliente o agregadas sobre el shortlist, no sobre la cartera completa — se perfilan en su propia fase con el mismo método |
| ¿`dim_producto` tiene fecha de alta del artículo? | **No** — solo vigencia SCD2/carga ETL (F0-3). "Nuevos productos" permanece fuera de alcance |
| Volumen real de cartera por vendedor activo | **Confirmado: máximo real 31.093 (`VEN01`)**, igual al techo de la auditoría 32 (F0-1) |

## Decisión (Fase 0)

Las 4 preguntas están cerradas. **Fase 1 autorizada para empezar** con una condición explícita:
la Fase 2 no se da por cumplida sin volver a correr `EXPLAIN ANALYZE` de `lista_trabajo` después de
aplicar la optimización de F0-2 y confirmar que el endpoint completo cumple `p95 < 800 ms`.

---

## Adenda — Fase 1 y Fase 2 aplicadas (2026-07-28)

### Fase 1 (cimientos BD + contratos): aplicada

Migración `0005_cartera360_ruta_inteligente` aplicada sobre el EDW real (`alembic upgrade head`,
`0004_ml_model_runs -> 0005_cartera360_ruta_inteligente`), 100% aditiva: `gestion_cartera_eventos`
gana `canal`/`resultado`/`proxima_accion_fecha`/`nota` (nullable) y su `CHECK` de `evento` amplía de
3 a 8 valores; tabla nueva `cartera_recordatorios`. Verificado con `\d` sobre ambas tablas — sin
pérdida de datos (la tabla tenía 0 filas, D-1). Corrección durante la aplicación: `evento` era
`varchar(20)` y el valor nuevo más largo (`interesado_sin_cierre`, 21 caracteres) no cabía —
ampliado a `varchar(30)` en la misma migración.

### Fase 2 (motor de priorización): aplicada, con 2 hallazgos de latencia nuevos

**F2-1 (Alta) — `PredictionRepository.get_rfm_features` escaneaba TODA `fact_ventas_detalle` (525k
filas) para responder por UN cliente.** Encontrado al perfilar `get_ruta_hoy` end-to-end (primera
medición: 5.37 s para 10 clientes, muy por encima del presupuesto). La causa: el CTE
`compras_por_dia` agregaba `(cliente_sk, fecha)` para TODOS los clientes antes de filtrar por el
`cliente_id` pedido — un `Seq Scan` completo (`EXPLAIN ANALYZE`: 366.2 ms de ejecución) en cada
llamada. Afecta a este método (`get_customer_segment`), que también sirve
`GET /analytics/ventas/clientes/{id}/segmento` y el detalle de Cartera 360 — **no era un problema
exclusivo del refactor, ya estaba en producción**. Corregido: resolver `cliente_sk` primero y
filtrar el CTE por él (usa `idx_fvd_cli`) — medido: **366.2 ms → 19.1 ms** (19x). Ajuste de
comportamiento acompañante: la query nueva devuelve 1 fila con `frequency=0` para un cliente sin
compras (antes devolvía 0 filas) — se añadió `if not res or res[1] == 0: return None` para
preservar la semántica "sin historial" exacta que ya consumía `get_customer_segment`.

**F2-2 (Media) — N+1 de segmentación/SHAP sobre el top 10 de la ruta.** `get_ruta_hoy` enriquece
hasta `CARTERA360_RUTA_TOP_N=10` clientes con segmento RFM y explicación SHAP de churn, cada uno
con su propia consulta + su propio `TreeExplainer` reconstruido. Corregido con el mismo patrón ya
establecido para el churn batch del two-stage (auditoría 32 H1): `PredictionRepository.
get_rfm_features_batch` + `PredictionService.get_customer_segment_batch`/`get_churn_explanation_
batch`, una consulta + una predicción/explicación vectorizada para los 10 clientes en vez de 10
round-trips.

**Resultado medido end-to-end** (`Cartera360Service.get_ruta_hoy`, proceso con el explainer SHAP ya
"calentado" — ver nota de warmup abajo): `VEN01` (31.093 clientes, peor caso real) **929.7 ms /
722.3 ms** en dos corridas sucesivas; `VEN03` (10.121) 637.2 ms; `VEN16` (2.187) 470.3 ms. **Mejora
total sobre la primera medición sin optimizar: 5.37 s → ~0.7-0.9 s (83-87%).**

**Pendiente, no bloqueante para Fase 1-2 pero documentado sin apelación (R-0: no ocultar lo que
falta):**
- El criterio de aceptación 7 del plan (`p95 < 800 ms`) se cumple en 2 de 3 corridas medidas de
  `VEN01` (el peor caso real) y no en la tercera (929.7 ms). Antes de dar Fase 2 por cerrada en
  producción falta: (a) un warmup explícito de `shap.TreeExplainer` en el `lifespan` del backend
  (el primer uso por proceso paga ~600 ms de import/JIT de la librería `shap` — confirmado
  aislando la medición: 614.5 ms la primera llamada, 5.6 ms la segunda sobre el mismo cliente; sin
  warmup, el primer usuario real del día paga ese costo), y (b) opcionalmente batchear también
  `get_product_recommendations`/`Cartera360Repository.get_perfil_cliente` (hoy siguen siendo 1
  consulta por cliente del top 10, ~30 ms c/u, ~300-600 ms acumulados) con el mismo patrón.
- No se investigó si `get_client_purchase_history`/`get_perfil_cliente` tienen el mismo bug de
  "agregar antes de filtrar" que F2-1 — ambos SÍ filtran por `cliente_id` en el `WHERE` antes de
  agrupar (revisados durante esta fase), a diferencia de `get_rfm_features`; no se encontró el
  mismo patrón, pero no se corrió `EXPLAIN ANALYZE` de cada uno individualmente.

**Validado:** `pytest tests/` completo (185 passed, 1 failed preexistente no relacionado — mismo
que la línea base, dependiente de fecha del sistema), suite específica de Notificaciones (21
passed, sin regresión de `NotificationService.get_lista_trabajo` — R-2 del plan), suite específica
de Cartera 360 heredada (3 passed, endpoints `/cartera360/*` sin cambios de contrato), suite completa
de integración (`-m integration`, 103 passed / 7 failed / 4 skipped — los 7 fallos son los mismos
preexistentes ya documentados en `CLAUDE.md`, ninguno toca código de esta fase), y nueva suite de
integración `tests/integration/test_cartera360_ruta_inteligente.py` (6 passed, 1 skipped por falta
de datos del vendedor seed en el EDW de prueba) cubriendo RLS 403 en los 2 endpoints por-cliente
nuevos (`timeline`, `gestion`) — criterio de aceptación 8 del plan.

### Fase 3 (frontend `/ventas/ruta`): aplicada

Archivos nuevos: `store/rutaVentasStore.ts` (Zustand, sin `persist` -- mismo criterio que
`crossSellStore`, trae PII real), 7 componentes en `components/rutaInteligente/` (`SmartKpiRow`,
`PriorityCard`, `RouteList`, `ClientDetailDrawer`, `QuickLogForm`, `ClientTimeline`,
`EffectivenessPanel`, `WeekPlanner`), `pages/VentasRuta.tsx` (orquestador, ~50 LOC). Extendidos sin
tocar contratos existentes: `types/cartera360.ts`, `services/cartera360.ts`, `hooks/cartera360.ts`,
`constants/queryKeys.ts`.

**Decisiones de implementación tomadas durante esta fase (no en el plan original, resueltas con el
mismo criterio de "no inventar/no sobre-construir"):**
- **DEC-1 revisada — `Sheet` lateral:** el componente `Drawer` ya existente (`components/ui/
  Drawer.tsx`, focus trap + Esc + portal) cubre exactamente lo que el plan llamaba "Sheet lateral
  nuevo" -- no se creó un primitivo nuevo, se reutilizó.
- **`RouteTable` sin virtualización:** el criterio de aceptación 1 ("≤10 clientes, sin scroll") ya
  implica que no hace falta virtualizar -- se implementó como `RouteList` (grid de `PriorityCard`),
  ver nota en el plan §8/criterio 12.
- **Score desglosado en 2 medidores independientes** (`PriorityCard`), nunca una barra apilada --
  mismo criterio que `ScoreDecompositionBar` de Venta Cruzada Fase 5 (el score final es
  `valor_historico × (1 + p_abandono/100)`, un producto, no una suma).
- **`/ventas/ruta` sin entrada en el Sidebar todavía:** `constants/permissions.ts` registra la ruta
  (accesible por URL directa) pero sin `nav`, reflejando en el frontend el mismo "dark launch" del
  backend (`CARTERA360_RUTA_INTELIGENTE_ENABLED=false`). Activar el flag + agregar `nav` es un
  cambio de una línea cuando se decida promover la Fase 7.

**Validado:** `tsc -b` limpio (build de producción completo, 908 ms, sin errores), `oxlint` sobre
el proyecto completo sin hallazgos nuevos (los 4 warnings preexistentes no tocan archivos de esta
fase), prueba end-to-end real vía `TestClient` con el usuario seed `ventas_gye@empresa.com`
autenticado (`login` 200, `GET /ruta/hoy` 200) -- el seed mapea a `codven='102'`, un código de
vendedor de prueba sin transacciones reales en el EDW (ya documentado como limitación conocida del
entorno de pruebas, no un bug), así que la respuesta trae 0 clientes con el contrato completo y
correcto (estado vacío real, sin excepción) -- el camino con datos reales ya se había validado
directamente contra el servicio con `VEN01` (10 clientes reales, nombres/valores reales) durante la
Fase 2. Verificación visual en navegador real sigue sin ser posible en este entorno Windows (sin
`chromium-cli`, limitación ya documentada en `CLAUDE.md`).

---

## Adenda — corrección post-despliegue (2026-07-28, mismo día)

Tras desplegar la Fase 3, el usuario reportó en pruebas reales de navegador: (a) no se veía ningún
cambio en el panel del vendedor, (b) el flujo de "Gestionar" no funcionaba, (c) el historial tampoco
funcionaba, y pidió reducir las 8 tarjetas del header a un máximo de 4.

### Hallazgo previo (no de este módulo) — frontend roto por dependencia faltante

El contenedor `bi_frontend` venía fallando en bucle desde ANTES de esta sesión: `framer-motion`
está declarado en `package.json` (usado por `Dropdown.tsx`/`Collapse.tsx`, trabajo previo no
relacionado con Cartera 360) pero nunca se instaló en la imagen -- `node_modules` no se
reconstruyó después de agregarlo. Esto explica por completo el punto (a): ningún cambio del
frontend era visible para nadie, no solo para este módulo. Corregido: `docker compose build
frontend` + `docker compose up -d frontend` (recreación necesaria; `docker compose restart` no
relee `.env` ni reconstruye la imagen). Se activó también `CARTERA360_RUTA_INTELIGENTE_ENABLED=true`
en `.env` (antes solo estaba activo en el entorno de tests) y se movió el `nav` del Sidebar de
`ventas.cartera360` a `ventas.ruta` (`Mi Ruta Inteligente`), tal como especifica §7 del plan
("el Sidebar apunta a la nueva desde la Fase 3").

### Hallazgo real — F3-1 (Alta): `get_timeline_cliente` usaba columnas inexistentes en `fact_devoluciones`

- **Evidencia:** `\d edw.fact_devoluciones` confirma que la tabla NO tiene `num_factura` ni
  `subtotal_neto` (columnas de `fact_ventas_detalle`, copiadas por error al escribir la query de
  Fase 4) -- tiene `num_nota_credito` y `total_linea_devolucion`. Reproducido en vivo con un
  cliente real de `VEN13`: `ProgrammingError: column f.num_factura does not exist`.
- **Impacto:** la pestaña "Historial" del panel de detalle devolvía 500 para TODO cliente, siempre
  -- este es el bug detrás del reporte (c). Como `QuickLogForm.onSuccess` cambia automáticamente a
  la pestaña "Historial" tras registrar una gestión, el usuario veía: envía el formulario -> la
  pantalla cambia a Historial -> error -- percibido como "Gestionar no funciona" (reporte b), aunque
  la gestión SÍ se había guardado correctamente (confirmado: existe una fila real en
  `public.gestion_cartera_eventos`, `usuario_id=9`, creada por el propio usuario desde el navegador
  antes de este fix).
- **Corrección:** `Cartera360Repository.get_timeline_cliente` reescrito con las columnas reales;
  verificado end-to-end contra un cliente real de `VEN13` -- 14 eventos devueltos (compras reales +
  la gestión del usuario), sin excepción.
- **Limpieza:** se insertaron 2 filas de prueba durante el diagnóstico (`usuario_id=1`, motivo
  "prueba diagnostico"); se eliminó solo esa (`id=3`). La fila real del usuario (`id=2`) se
  conservó intacta.

### Aplicado — reducción de tarjetas del header a 4

`SmartKpiRow.tsx`: de 8 tarjetas a 4 (Clientes con alerta hoy, Ingreso potencial en riesgo, Valor
potencial de la ruta de hoy, Avance del día -- esta última ahora incluye la meta diaria como
referencia en el subtítulo en vez de ocupar una tarjeta separada). Las 3 tarjetas retiradas
(`clientes_asignados`, `clientes_recuperados_mes`, `oportunidades_activas`) siguen calculándose en
`TarjetasHeader` sin cambio de contrato -- solo se dejaron de renderizar en esta fila.

### Aplicado — manual de usuario y desarrollador

`docs/manual_ruta_inteligente_ventas.md` (nuevo), mismo formato en 2 partes que
`docs/manual_metas_y_comisiones.md`: Parte 1 explica qué hace el módulo, cómo leer cada tarjeta y
cada panel, y qué NO hace a propósito; Parte 2 documenta arquitectura, archivos, endpoints,
configuración, los 4 bugs reales encontrados durante la construcción (incluyendo F3-1 de esta
adenda) y cómo extender el módulo.

**Validado:** `tsc --noEmit` limpio, `oxlint` sin hallazgos nuevos, prueba end-to-end real (timeline
+ efectividad + plan semanal) contra un cliente real de `VEN13` con el grafo completo de modelos
SQLAlchemy cargado (mismo estado que un request real de FastAPI). Backend `/health` responde
`modelos_ml_listos: true` tras el fix (hot-reload de uvicorn, sin necesidad de reconstruir la
imagen del backend).

---

## Adenda 2 — rotación de la ruta + regresión real de `shap`/`numpy` (2026-07-29)

### Mejora de producto — F3-2: la ruta no rotaba entre días

**Pregunta del usuario:** "¿qué pasa si el vendedor ya aplicó/gestionó a un cliente, los mismos
clientes siguen apareciendo o deberían rotar?" -- diagnóstico correcto: `get_ruta_hoy` rankeaba
solo por `valor_historico × (1 + probabilidad_abandono)`, ninguno de los dos cambia de un día para
otro solo porque el vendedor ya actuó. Sin exclusión explícita, los mismos `CARTERA360_RUTA_TOP_N`
clientes habrían reaparecido todos los días, sin que el resto de la cartera reciba cobertura real.

**Corrección aplicada** (`Cartera360Service.get_ruta_hoy`): antes de tomar los `CARTERA360_RUTA_
TOP_N` finales, se descarta del pool de `CARTERA360_RUTA_POOL_FILTRADO` (50 por defecto) candidatos
ya rerankeados:
- cualquier cliente con una gestión registrada **hoy** (cualquier resultado -- reaparece mañana si
  el riesgo/valor lo siguen justificando);
- cualquier cliente con `proxima_accion_fecha` en el **futuro** (ya se prometió un seguimiento en
  una fecha concreta -- una fecha vencida u hoy mismo sigue elegible, es una acción debida, no se
  excluye).

Repositorio nuevo: `Cartera360Repository.get_ultima_gestion_por_cliente_ids` (reemplaza al método
anterior `get_ultima_gestion_por_clientes`, que requería resolver `cliente_sk` por cliente uno por
uno antes de poder consultarlo -- el nuevo resuelve todo en una sola consulta por `cliente_id`,
eliminando ese N+1 de paso). Setting nuevo: `CARTERA360_RUTA_POOL_FILTRADO=50`.

**Validado en vivo, cruzando un día real:** se registró una gestión de prueba para el cliente
`206988` (cartera de `VEN13`) el 2026-07-28; `get_ruta_hoy('VEN13')` ese mismo día lo excluyó
correctamente de los 10 resultados. Al re-ejecutar el 2026-07-29 (día siguiente real, sin acción
adicional), el mismo cliente **reapareció** en la ruta -- confirma que la exclusión es por día, no
permanente, exactamente el comportamiento de rotación pedido.

### Regresión real encontrada durante la prueba — F3-3 (Alta): `shap` no estaba instalado en la imagen

Al probar la corrección de rotación con el grafo completo de la app cargado, `PredictionService.
get_churn_explanation_batch` falló con `No module named 'shap'` en el contenedor real `bi_backend`.
Causa: `shap` se había instalado **en vivo** dentro del contenedor en una sesión anterior (ver nota
"pendiente de confirmar con una reconstrucción completa de la imagen" en `CLAUDE.md`, actualización
2026-07-28 Fase 6) -- nunca se reconstruyó la imagen con `shap` en `requirements.txt` realmente
horneado. Cuando esta misma sesión recreó el contenedor backend (`docker compose up -d backend`,
necesario para tomar `CARTERA360_RUTA_INTELIGENTE_ENABLED` del `.env`), Docker levantó la imagen
vieja sin `shap` -- la instalación en vivo no sobrevive a la recreación del contenedor.

**Segunda regresión, encontrada al reconstruir la imagen:** `docker compose build backend` instaló
`shap==0.46.0` correctamente, pero `import shap` seguía fallando -- esta vez con
`TypeError: Converting np.inexact or np.floating to a dtype not allowed`, dentro de
`shap/plots/colors/_colorconv.py` (código heredado de skimage que `shap/__init__.py` importa
incondicionalmente, aunque este proyecto solo usa `TreeExplainer`, nunca los gráficos). Causa raíz:
`requirements.txt` no fijaba una versión de `numpy`, así que `pip` resolvió `numpy==2.4.6`
(compatible con pandas/scikit-learn/xgboost, pero **no** con el código de color heredado de
`shap==0.46.0`, que llama `np.dtype(np.floating)` -- numpy≥2.3 lo rechaza).

**Corrección:** `numpy<2.3` agregado a `backend/requirements.txt`, con el hallazgo documentado
in-line. Reconstruida la imagen (`numpy==2.2.6` resuelto), `import shap` limpio, `TreeExplainer`
verificado end-to-end (el campo `motivo` de `get_ruta_hoy` vuelve a incluir señales SHAP reales,
ej. "señales de riesgo del modelo: frequency, recency").

**Validado:** `pytest tests/` (185 passed, 1 failed preexistente no relacionado, mismo de siempre),
`docker exec bi_backend python -c "import shap"` limpio, prueba end-to-end de `get_ruta_hoy` con
SHAP real funcionando. `pytest` no estaba disponible en la imagen reconstruida (`requirements-dev.txt`
tampoco se hornea en el `Dockerfile`, por diseño -- imagen tipo producción); se instaló en vivo para
esta corrida, consistente con el patrón ya documentado del proyecto para dependencias de solo-test.
