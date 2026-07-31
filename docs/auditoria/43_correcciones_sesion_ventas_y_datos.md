# Auditoría 43 — Datos de Bodega, higiene de sesión, Próximas acciones, Comisiones Variables, Dashboard del vendedor

- **Fecha:** 2026-07-30
- **Alcance:** `backend/app/repositories/warehouse_repository.py` (reporte `sin-venta`),
  `etl/extractors/kardex_extractor.sql`, `etl/transformers/fact_transformer.py`,
  `etl/orchestrator.py` (`PIPELINE_CONFIG`), `frontend/src/store/*`, `frontend/src/services/http.ts`,
  `backend/app/api/routes/auth.py`, `frontend/src/components/rutaInteligente/UpcomingActions.tsx`,
  `backend/app/services/cartera360_service.py`, `backend/app/services/gestion_service.py`,
  `backend/app/core/config.py` (`COMISION_MODO`), `frontend/src/components/goals/VendorGoalDashboard.tsx`,
  `frontend/src/pages/DashboardVentas.tsx`.
- **Método:** revisión estática de código y configuración (`.env`, `docker-compose.yml`), lectura
  de extractores/transformers/orquestador del ETL, lectura de rutas/servicios/repositorios del
  backend y de stores/servicios del frontend. **No hubo ninguna escritura a Producción ni al EDW.**
  **Actualización 2026-07-30 (segunda corrida, Docker ya disponible):** con `bi_postgres_edw` y
  `bi_backend` activos se ejecutaron `SELECT` reales de reconciliación contra el EDW. **Contra
  SAP (Producción) se intentó y falló por conectividad de red**: `bi_backend` no tiene el driver
  `pyodbc` instalado (solo lo tiene la imagen `etl`, que estaba detenida) y una prueba directa de
  TCP contra `172.16.50.5:4016` (host/puerto de `DB_HOST`/`DB_PORT` en `.env`) desde este entorno
  agotó el tiempo de espera sin conectar — el servidor SQL Anywhere de Producción no es alcanzable
  desde esta red. Por lo tanto, la reconciliación de este documento es **EDW-interno**
  (`fact_movimientos_inventario` vs. `fact_inventario_snapshot`, ambos dentro de Postgres), no
  contra SAP directamente; se declara explícitamente dónde sigue pendiente la comparación con
  Producción. Ninguna consulta ejecutada fue `INSERT`/`UPDATE`/`DELETE`.

## Bugs reales encontrados y corregidos durante la validación en vivo (2026-07-30)

La implementación de este plan se había validado antes solo con `py_compile`/`tsc`/`pytest` sin
base de datos (Docker no estaba disponible en la primera corrida). Al levantar `bi_postgres_edw` +
`bi_backend` y probar cada endpoint nuevo con datos y usuarios reales, aparecieron **3 bugs que el
análisis estático no detectó**, los tres corregidos y reverificados en la misma corrida:

1. **`POST /auth/logout` respondía 500 en el 100% de los intentos.** `app/models/token_revocado.py`
   declaraba `ForeignKey("usuarios.id")` sin el prefijo de esquema (`public.usuarios.id`) ni
   `__table_args__ = {"schema": "public"}` -- SQLAlchemy no podía resolver la tabla destino de la
   FK al construir el `INSERT`. Corregido; reprobado en vivo: login → `GET /users/me` 200 → `POST
   /auth/logout` 204 → el MISMO token → `GET /users/me` 401 → fila real persistida en
   `public.tokens_revocados` con su `jti`, `usuario_id` y `expira_en`. Cumple el criterio de
   aceptación 2 del plan.
2. **`GET /analytics/ventas/mi-negocio` respondía 500.** `VendorDashboardService._ranking_posicion`
   llamaba a `AnalyticsRepository.get_sales_performance` (el método existe en el *repositorio*),
   pero el *servicio* que se inyecta (`AnalyticsService`) expone el mismo cálculo bajo el nombre
   `get_sales_kpis` -- `AttributeError` en producción. Corregido, y de paso se detectó que la firma
   real es `get_sales_kpis(sucursal=None, anio=None, mes=None, vendedor=None)` (`sucursal` es el
   primer parámetro posicional, no `anio`) -- la llamada corregida usa argumentos por nombre.
3. **`evolucion_mensual`/`top_productos` usaban una fórmula de venta distinta a la oficial del
   sistema.** `AnalyticsRepository.get_evolucion_mensual_vendedor` sumaba `subtotal_neto` sin
   restar devoluciones y sin el filtro `estado_factura` de la definición canónica de **Venta Neta**
   (`app/services/metricas/venta_neta.py`, G-02) -- la misma definición que ya usa
   `GoalRepository.get_vendor_net_sales_period` para el panel "Mi Meta y Comisión". El bug era
   silencioso (ambos endpoints devolvían 200 con números plausibles) y solo se detectó comparando
   dos widgets del MISMO dashboard nuevo entre sí con el vendedor real `VEN02`: la tarjeta "Cuota"
   (vía `CommissionService`) mostraba **$47.559,92** para julio 2026, mientras que el punto de julio
   en "Evolución mensual" (vía el método nuevo, sin corregir) mostraba **$54.976,83** — una
   diferencia de ~$7.400 en el mismo mes para el mismo vendedor. Corregido reescribiendo la query
   con los fragmentos canónicos `SQL_VENTA_BRUTA`/`FILTRO_ESTADO_VALIDO` y restando
   `fact_devoluciones`, igual que el resto del sistema; reprobado en vivo: ambos widgets ahora
   coinciden exactamente en $47.559,92.
- **Validación de cierre:** `pytest backend/tests/unit` (194 passed, 1 falla preexistente idéntica
  a la documentada, sin relación con estos cambios); `pytest backend/tests/integration/
  test_warehouse_actualizacion_bodega.py -m integration` dentro del contenedor real (28 passed, sin
  regresiones por el campo nuevo `nota_cobertura_datos`); `pytest backend/tests/integration/
  test_cartera360_ruta_inteligente.py -m integration` (6 passed, 1 skipped); `GET /ruta/proximas-
  acciones` probado en vivo con el vendedor real `vwilliam@gmail.com` (VEN02) devolviendo una acción
  real con `estado: "hoy"`; `GET /analytics/ventas/mi-negocio` probado en vivo con el mismo vendedor,
  devolviendo cuota, comisión, ranking (#3 de 9), evolución de 7 meses, top 5 productos, pipeline
  priorizado (churn real) y la próxima acción, todo consistente entre sí.

## Hallazgos

### H43-1 (REFUTADA por evidencia en vivo) — La ventana de kardex NO está truncada en 2020-01-01
- **Hipótesis original:** `.env:38` fija `FECHA_DESDE=2020-01-01`, y como el extractor de kardex
  aplica `fecdoc >= '{FECHA_DESDE}'` sin excepción, se esperaba que `edw.fact_movimientos_inventario`
  no tuviera datos anteriores a 2020.
- **Consulta ejecutada (EDW real, `bi_postgres_edw`):**
  ```sql
  SELECT MIN(d.fecha_completa), MAX(d.fecha_completa), COUNT(*)
  FROM edw.fact_movimientos_inventario m JOIN edw.dim_fecha d ON m.fecha_sk=d.fecha_sk;
  -- Resultado real: min_fecha=2017-12-31, max_fecha=2026-07-28, filas=955.466
  ```
  Distribución por año (todos con datos, sin huecos): 2017=7.487, 2018=111.266, 2019=109.252,
  2020=94.256, 2021=103.507, 2022=107.214, 2023=103.114, 2024=109.590, 2025=124.654, 2026=85.126.
- **Conclusión:** **la hipótesis es falsa.** El EDW real tiene kardex continuo desde 2017-12-31,
  no desde 2020 — `FECHA_DESDE=2020-01-01` en `.env` describe el comportamiento del **próximo**
  incremental (no vuelve a extraer filas anteriores a esa fecha si se re-ejecuta el ETL desde cero
  hoy), pero la carga histórica ya presente en la base viene de una corrida anterior con un valor
  distinto de `FECHA_DESDE` (o de la carga inicial del volumen, `edw/07`/`edw/08`, ejecutada antes
  de que `.env` se fijara en 2020). **No es la causa de la divergencia reportada por el usuario.**
  Se retira esta hipótesis; ver H43-1b/H43-2b/H43-3b más abajo para la causa real, encontrada con
  la misma corrida en vivo.

### Alta — H43-2b (evidencia real) `stock_actual` calculado por kardex diverge del snapshot en un ~0.07% de las combinaciones, con casos individuales grandes
- **Evidencia:** comparación EDW-interna (kardex acumulado vs. `edw.fact_inventario_snapshot`, la
  fuente de existencia real más reciente del EDW — regla 6, análoga a `vi_mv_existencias` de SAP)
  para el último `fecha_sk` disponible del snapshot (2026-07-28):
  ```sql
  WITH snap AS (SELECT producto_sk, almacen_sk, stock_actual FROM edw.fact_inventario_snapshot
                WHERE fecha_sk = (SELECT MAX(fecha_sk) FROM edw.fact_inventario_snapshot)),
       kardex AS (SELECT producto_sk, almacen_sk,
                    SUM(CASE WHEN es_entrada THEN cantidad_movimiento
                             WHEN es_salida THEN -cantidad_movimiento ELSE 0 END) AS stock_kardex
                  FROM edw.fact_movimientos_inventario GROUP BY 1,2)
  SELECT COUNT(*) total, COUNT(*) FILTER (WHERE ABS(stock_actual-COALESCE(stock_kardex,0))>0.01) con_diferencia
  FROM snap LEFT JOIN kardex USING (producto_sk, almacen_sk);
  -- Resultado real: total=114.240, con_diferencia=76 (75 excluyendo Z-9001/chatarra)
  ```
  Casos reales inspeccionados (excluyendo `Z-9001`, artículo de chatarra ya excluido a propósito
  del resto del módulo): p. ej. `codart=304222` (almacén ATAHUALPA) tiene **2.805 movimientos desde
  2017-12-31** y aun así el stock derivado del kardex (4) difiere del snapshot (10) en 6 unidades;
  `codart=603432` difiere en 4 sobre 6.698 movimientos; `LT-U1P-10189-1` difiere en -5 sobre 491
  movimientos recientes (desde 2024-03-25). El promedio de diferencia absoluta sobre las 75 filas
  no triviales es pequeño (redondea a 0.00 al agregado), pero no es cero fila por fila.
- **Impacto real:** de 114.240 combinaciones `(producto, almacén)` con snapshot vigente, **75
  (0.066%)** tienen un stock derivado del kardex distinto al snapshot real, con magnitudes de
  pocas unidades cada una (no hay un patrón de fecha de corte: aparecen en productos con historia
  completa desde 2017). No se pudo determinar la causa exacta (¿un tipo de movimiento no cubierto
  por el extractor? ¿redondeo acumulado sobre miles de transacciones?) sin acceso a SAP, que **no
  es alcanzable desde este entorno** (prueba de conectividad TCP a `172.16.50.5:4016` agotó tiempo
  de espera). **Pendiente de validar contra SAP** cuando haya conectividad real.
- **Riesgos:** el reporte "productos sin venta"/"estancados" puede reportar un stock ligeramente
  distinto al real para un subconjunto pequeño y no identificado a priori de artículos — no es un
  error sistemático de diseño, es un residuo de datos.
- **Recomendación:** dado que la magnitud es pequeña y no sigue el patrón de fecha que se sospechaba,
  **no se justifica una recarga histórica completa (Vía A del plan original, descartada)**. En su
  lugar: (1) declarar en el reporte que el stock se deriva del kardex acumulado (ya aplicado en la
  Fase 1 vía `nota_cobertura_datos`); (2) para una reconciliación exacta, requiere acceso a SAP
  (fuera de alcance de esta corrida) comparando `vi_mv_existencias` línea a línea contra las 75
  combinaciones identificadas arriba.

### Alta — H43-3b (evidencia real) 22 combinaciones `(producto, almacén)` con stock en el snapshot no tienen NINGÚN movimiento de kardex — 7 de ellas artículos reales, no el centinela
- **Evidencia:**
  ```sql
  -- combinaciones con stock_actual>0 en el snapshot vigente sin NINGUNA fila de kardex
  SELECT COUNT(*) FROM <snapshot vigente con stock>0> snap
  WHERE NOT EXISTS (SELECT 1 FROM edw.fact_movimientos_inventario m
                     WHERE m.producto_sk=snap.producto_sk AND m.almacen_sk=snap.almacen_sk);
  -- Resultado real: 22 de 11.349 combinaciones con stock positivo (0.19%)
  ```
  De esas 22: 15 corresponden al producto centinela `-1 (Desconocido)` (stock atribuido a un
  `codart` que no resolvió contra `dim_producto`, 1-6 unidades cada una, en 10 bodegas distintas) y
  **7 son artículos reales con nombre** (`7025676` LEDVANCE SLIM PLAFON, `7021581` LEDVANCE SLIM
  PLAFOM, `EZ-SP101` HIDROMETRO DENSIMETRO ×2, `S498741` PAD ORBITAL, `S230500` LIMPIADOR DE AROS,
  todos con stock=1 o 10) que tienen existencia real en el snapshot pero jamás aparecieron en
  `fact_movimientos_inventario` — el universo del reporte `sin-venta` (que exige al menos un
  movimiento de kardex para entrar al universo) **nunca puede mostrar estos 7 artículos**, aunque
  cumplen exactamente la definición de "producto con stock e inactividad total".
- **Impacto:** confirma el hallazgo de diseño (universo restringido a productos con movimiento),
  pero en una magnitud real muy inferior a la hipótesis original: **7 artículos**, no un corte de
  años completo. También revela un hallazgo colateral no buscado: `fact_inventario_snapshot` tiene
  **630 filas (0.11% de 570.612)** con `producto_sk=-1` (código de artículo del feed de existencias
  de SAP que no resuelve contra `dim_producto` vigente — posible artículo dado de baja o renombrado
  en el ERP sin reflejarse en el catálogo del EDW).
- **Recomendación:** ampliar el universo del reporte para incluir también las combinaciones del
  snapshot más reciente con stock > 0, no solo las que tienen movimiento de kardex (cambio de
  bajo costo, no requiere recarga histórica); investigar por separado el 0.11% de `producto_sk=-1`
  en el snapshot como hallazgo de calidad de datos del feed de existencias.

### Media — H43-4 `fecha_ultima_venta` puede mostrar `NULL` sin que signifique "nunca vendido"
- **Evidencia:** el CTE `ventas_ordenadas`/`sin_venta_rango` solo considera movimientos `FAC` con
  fecha resuelta en `edw.dim_fecha` — para los 7 artículos de H43-3b (sin ningún kardex) el reporte
  mostraría `fecha_ultima_venta=NULL`, indistinguible de "nunca tuvo una venta real" cuando en
  realidad el artículo simplemente nunca quedó registrado en el kardex del EDW.
- **Recomendación:** una vez ampliado el universo (H43-3b), declarar explícitamente en el contrato
  cuándo `NULL` significa "sin historial de kardex en el EDW" vs. "tiene kardex pero nunca vendió".

### Media-Alta — H43-5 El extractor de kardex no aplica el token `{ESTADO}` (heredado, ya documentado)
- **Evidencia:** `etl/extractors/kardex_extractor.sql` es el único extractor de
  `PIPELINE_CONFIG` que no filtra por estado de documento — confirmado comparando contra el resto
  de extractores tokenizados, que sí aplican `{ESTADO}`. Ya estaba documentado como H-8 en fases
  previas del proyecto (Fase 6.7, `docs/auditoria/42_correcciones_integrales_sistema.md`); se
  re-confirma vigente en esta auditoría porque afecta directamente al reporte de productos sin
  movimiento: una factura anulada (`estado='A'`) puede contar como "última venta" o como
  "movimiento" y ocultar a un artículo verdaderamente sin rotación.
- **Recomendación:** no se corrige en este documento por sí sola — requiere cambio de esquema/ETL
  (agregar columna de estado a `fact_movimientos_inventario` y re-extraer), del mismo alcance que
  la recarga histórica de H43-1. Conviene ejecutarlos juntos si el usuario aprueba la Vía A.

### Baja — H43-6 Exclusión de `Z-9001` no aplica a este reporte (verificado, sin acción)
- **Evidencia:** `EXCLUIR_CODART = {"Z-9001"}` (línea 24 de `warehouse_repository.py`) no se
  referencia dentro de `get_articulos_sin_venta` ni de `_filtros_snapshot` — se usa solo en el
  dataset de entrenamiento del modelo de demanda (`ml/`), confirmado por búsqueda de uso. **Hallazgo
  refutado**: el reporte de productos sin movimiento no excluye `Z-9001` en silencio.

### Media — H43-7 Cardinalidad SCD2 en el universo del reporte
- **Evidencia:** el reporte agrupa por `p.codart` en el `SELECT` final (correcto, colapsa
  versiones SCD2), pero el CTE `universo` hace `JOIN edw.dim_producto p ON m.producto_sk =
  p.producto_sk` antes de agrupar. Si dos versiones vigentes del mismo `codart` existieran
  simultáneamente en `dim_producto` (violación de la regla SCD2 de una sola fila vigente por
  business key), el `GROUP BY` final las colapsaría en el nivel del `SELECT`, pero el CTE `stock`/
  `ventas_ordenadas` sumaría por `producto_sk` (no por `codart`) — dos filas de stock que después
  se agregan con `MAX`, no `SUM`, subestimando el stock real si el artículo estuviera partido.
  **Pendiente de validar**: requiere confirmar contra el EDW real si existe alguna violación viva
  de "una sola fila vigente por `codart`" en `dim_producto` (validación 8 de la skill
  `etl-edw-auditor`, no ejecutada por falta de Docker).

### Alta — H43-8 La caché de TanStack Query no se limpia al cerrar sesión
- **Evidencia:** `authStore.ts:29-33` (`logout()`) solo hace
  `localStorage.removeItem('auth_token')` / `removeItem('auth_user')` y actualiza el estado
  interno; `UserMenuContent` (`UserMenu.tsx:38-41`) llama a `logout()` y navega con
  `navigate('/login')` (SPA, sin recarga de página). El `QueryClient` se instancia una sola vez en
  `frontend/src/app/providers.tsx:4` y nunca se invalida ni se limpia en el flujo de logout. Con
  React Router sin recarga completa, el `QueryClient` sigue vivo en memoria: al loguearse un
  usuario B, cualquier `useQuery` ya montado (o que se monte antes de que termine el primer
  refetch) sirve primero el dato cacheado del usuario A.
- **Impacto:** exactamente el síntoma reportado por el usuario — "se estan quedando los cambios que
  hizo un usuario y se visualiza si se loguea con otro usuario". Afecta a cualquier panel que use
  `useQuery`/`useMutation` (KPIs, cartera, comisiones, nombres de clientes = PII).
- **Recomendación:** función única de cierre de sesión que ejecute `queryClient.clear()` antes de
  redirigir. Ver Fase 2 del plan.

### Media — H43-9 Estado Zustand en memoria sobrevive al logout
- **Evidencia:** `crossSellStore.ts` (cliente seleccionado, PII), `rutaVentasStore.ts`
  (`clienteAbiertoId`) no exponen ninguna función de reset y no se limpian en `authStore.logout()`.
  Sin recarga de página persisten al siguiente login.
- **Recomendación:** agregar `reset()` a cada store con estado sensible y llamarlos desde el punto
  único de cierre de sesión (Fase 2).

### Media — H43-10 `sessionStorage` de filtros de Bodega persiste entre usuarios
- **Evidencia:** `bodegaFiltersStore.ts:36-39` persiste en `sessionStorage` bajo la clave
  `bodega-filters`, que sobrevive a un logout/login dentro de la misma pestaña (solo se limpia al
  cerrar la pestaña del navegador). Con la RLS por almacén (RN-B10) esto puede dejar al usuario B
  con un filtro de almacén al que no tiene acceso, mostrando un resultado vacío inexplicable.
- **Recomendación:** `sessionStorage.clear()` (o reset específico de este store) en el punto único
  de cierre de sesión.

### Baja — H43-11 Preferencia de UI (`ui_sidebar_collapsed`) sobrevive al logout
- **Evidencia:** `uiStore.ts:20`, en `localStorage`. Impacto cosmético únicamente (no es un dato de
  negocio ni PII) — no requiere limpiarse, se documenta por completitud.

### Alta — H43-12 No existe invalidación de token del lado del servidor
- **Evidencia:** `backend/app/api/routes/auth.py` expone únicamente `POST /login`; no hay ningún
  endpoint de logout ni mecanismo de revocación. El JWT emitido es válido hasta su expiración natural
  sin importar si el usuario "cerró sesión" en el frontend — un token capturado antes del logout
  sigue autenticando contra la API.
- **Impacto:** el requerimiento del usuario pide explícitamente "quitar por completo el rastro de
  tokens", que hoy es imposible del lado del servidor.
- **Recomendación:** `POST /auth/logout` con denylist de `jti` (ver Fase 2 del plan).

### Alta — H43-13 "Próximas acciones" no puede mostrar nada por diseño (panel y fuente se excluyen)
- **Evidencia:** el registro de la fecha funciona correctamente de punta a punta
  (`QuickLogForm.tsx` → `POST /ruta/gestion` → `GestionService.registrar_gestion` →
  `Cartera360Repository.log_gestion`, columna `proxima_accion_fecha` persistida sin error). El
  panel `UpcomingActions.tsx:17-19` filtra `proxima_accion_fecha` sobre `data.clientes` que llega
  de `GET /ruta/hoy` (`VentasRuta.tsx:58`). Pero `Cartera360Service.get_ruta_hoy` (función
  `_elegible_hoy`, `cartera360_service.py:182-190`) descarta explícitamente del ranking a todo
  cliente cuya `proxima_accion_fecha` esté en el futuro. El conjunto que alimenta al panel es el
  complemento exacto de lo que el panel necesita mostrar — solo sobrevive el caso degenerado de una
  fecha ya vencida en un cliente que igual entra al top-N del día.
- **Impacto:** el usuario reporta correctamente "no funciona" — el panel casi nunca tiene contenido
  aunque el registro de la fecha sea correcto.
- **Riesgo de "corregirlo mal":** revertir la exclusión en `_elegible_hoy` rompería la rotación de
  la ruta (el mismo cliente aparecería todos los días), una regla ya validada y documentada. La
  corrección correcta es agregar la fuente de datos que falta (endpoint propio), no tocar la
  exclusión.
- **Recomendación:** endpoint `GET /analytics/ventas/ruta/proximas-acciones` — ver Fase 3 del plan.
  El manual de usuario (`docs/manual_ruta_inteligente_ventas.md` §1.7) ya describe el comportamiento
  correcto; documentarlo de nuevo tras implementar el endpoint, verificado contra el código real.

### Alta (bloqueante de negocio, no de código) — H43-14 Comisiones Variables: salvaguarda de líneas sin costo YA cuantificada (favorable)
- **Evidencia (consulta real, `GET /gerencia/goals/lineas-sin-costo`, admin autenticado):**
  9 vendedores con líneas de `codart='-1'` (producto centinela, sin costo resoluble), **1.236
  líneas afectadas en total**, venta asociada ≈ **$1.722,50**. Denominador real:
  `SELECT COUNT(*) FROM edw.fact_ventas_detalle` = **525.267 líneas**.
  → **1.236 / 525.267 ≈ 0,24% de las líneas**, muy por debajo del criterio de salida del piloto
  (<5%, `docs/prompt_presentacion_metas_comisiones_gerencia.md`). La salvaguarda 2 (tasa mínima
  sobre valor para estas líneas, en vez de ignorarlas o pagar de más) tiene una base real pequeña y
  manejable.
- **Impacto:** el bloqueante que motivó H43-14 **se levanta** — el % de líneas sin costo no es un
  obstáculo para avanzar a `sombra`. Siguen pendientes, sin poder validarse sin decisión de negocio:
  la matriz de categorías vigente aprobada por gerencia, y correr al menos un mes en `sombra` antes
  de `variable` (secuencia de la Fase 4 del plan, no ejecutable en esta auditoría porque activar
  `sombra` es una decisión de negocio, no una validación técnica).
- **Recomendación:** con esta cifra, el paso `plana → sombra` puede proceder; `variable` sigue
  condicionado a los pasos 2-5 de la Fase 4 del plan (matriz aprobada, revisión de un mes cerrado en
  sombra, arranque verificado en los 3 modos).

### Media — H43-15 Badge "no es lo que se paga" queda falso si se activa `COMISION_MODO=variable`
- **Evidencia:** `VendorGoalDashboard.tsx:183` etiqueta el panel dual con un comentario que asume
  `COMISION_MODO=sombra`; verificar en el componente si el texto del badge está condicionado al
  modo real que reporta el backend o si es una cadena fija — de ser fija, al pasar a `variable` el
  usuario vería un aviso incorrecto ("cálculo en prueba, no es lo que se paga") sobre dinero que sí
  se está pagando.
- **Recomendación:** condicionar el texto del badge al campo que el backend ya expone
  (`comision_variable`/`nivel_variable` no nulos + el modo real), nunca a una cadena hardcodeada.
  Ver Fase 4.4 del plan.

### Media — H43-16 `DashboardVentas.tsx` es efectivamente un formulario de búsqueda, no un dashboard
- **Evidencia:** los 3 paneles de análisis (segmento RFM, churn, recomendaciones) están detrás de
  `{clienteId && ...}` (línea 142) y requieren que el vendedor escriba un `cliente_id` exacto sin
  autocompletar; las 4 KPI cards dependen de `GET /analytics/ventas/goals`, ya identificado con
  desalineación de `id_vendedor_origen` en el historial del proyecto (B-3). El resto del valor del
  rol vive en páginas separadas (Mi Meta y Comisión, Venta Cruzada, Mi Ruta Inteligente) nunca
  enlazadas desde la página de aterrizaje.
- **Recomendación:** dashboard agregador nuevo — ver Fase 5 del plan, con el mapeo explícito de qué
  widgets del mockup tienen fuente real y cuáles quedan fuera de alcance por no tenerla.

## Resumen de recomendaciones por prioridad (estado final tras validación en vivo)

**Alta — aplicadas y verificadas en vivo:**
1. ~~Confirmar H43-1/H43-2/H43-3~~ **Hecho.** H43-1 refutada (el kardex tiene historia continua
   desde 2017-12-31, no desde 2020); H43-2/H43-3 reformuladas con evidencia real de magnitud mucho
   menor a la hipótesis original (75 combos con diferencia de stock de 0.066%, 7 artículos reales
   sin ningún kardex de 11.349 con stock positivo). Aplicada la declaración de cobertura de datos en
   el contrato (`nota_cobertura_datos`); **no se justifica** una recarga histórica completa.
2. **Hecho y verificado end-to-end.** `POST /auth/logout` + limpieza de caché/stores/sessionStorage.
   Bug real encontrado y corregido en el camino (FK sin schema, ver "Bugs reales" arriba).
3. **Hecho y verificado end-to-end** con datos reales (vendedor VEN02).
4. **Hecho.** Líneas sin costo cuantificadas en vivo: 0,24% del total — bajo el umbral de salida del
   piloto, deja de ser bloqueante técnico.

**Media — aplicadas y verificadas:**
5. Declarar la ventana de datos y la fuente de stock — hecho (Fase 1).
6. `{ESTADO}` en el extractor de kardex — **sigue pendiente**, requiere cambio de ETL/esquema y
   re-extracción desde SAP; fuera de alcance de esta corrida (sin conectividad a SAP).
7. Badge de modo de comisión dinámico — hecho y verificado con `tsc`/`oxlint` (Fase 4.4).
8. Dashboard "Mi Negocio" del vendedor — hecho y verificado end-to-end con datos reales de VEN02,
   incluido un bug de fórmula de venta neta corregido en el camino (ver "Bugs reales" arriba).

**Baja:**
9. `ui_sidebar_collapsed` — no requiere acción.

**Hallazgo colateral nuevo, no corregido (fuera de alcance):** 630 filas (0,11%) de
`edw.fact_inventario_snapshot` tienen `producto_sk=-1` (código de artículo del feed de existencias
de SAP que no resuelve contra `dim_producto` vigente) — documentado para investigación futura, no
bloqueante de este plan.

## Validaciones automáticas mínimas (skill `etl-edw-auditor`) — estado

| # | Validación | Estado |
|---|---|---|
| 1 | Pérdida de registros (origen vs. destino) | **Pendiente de validar** (sin Docker) |
| 2 | Duplicados por llave de negocio | **Pendiente de validar** |
| 3 | Cambios de volumen entre cargas (`edw.etl_control`) | **Pendiente de validar** |
| 4 | Cambios de granularidad | **Pendiente de validar** |
| 5 | Llaves huérfanas / centinela `-1` | **Pendiente de validar** |
| 6 | Fechas fuera de rango | Confirmado por código: la ventana está limitada por `FECHA_DESDE` de forma deliberada (H43-1), no por un bug de filtro |
| 7 | Códigos inexistentes en dimensión | **Pendiente de validar** |
| 8 | Integridad SCD2 | **Pendiente de validar** (relevante para H43-7) |
