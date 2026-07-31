# Plan — Datos de Bodega, higiene de sesión, Próximas acciones, Comisiones Variables y Dashboard del Vendedor

- **Fecha:** 2026-07-30
- **Origen:** requerimientos del usuario (6 puntos) recogidos en esta sesión.
- **Auditoría previa obligatoria (Fase 0):** `docs/auditoria/43_correcciones_sesion_ventas_y_datos.md`
  (siguiente número libre; el último aplicado es `42_correcciones_integrales_sistema.md`).
- **Skills a usar por fase:** `etl-edw-auditor` (Fase 1, obligatoria antes de tocar `etl/` o `edw/`),
  `backend-ml-serving` (Fase 5, donde el dashboard consume `churn_rf`/`recommendation`),
  `frontend-design` + `dataviz` (Fase 5, diseño y gráficos del dashboard nuevo).

## Invariantes (no negociables en todo el plan)

1. **Producción SAP es SOLO LECTURA.** Toda validación contra el ERP es `SELECT` puro.
2. **Ningún campo de ningún response puede ser simulado, inventado o rellenado con placeholder.**
   Restricción explícita que el usuario ya impuso en el refactor de Venta Cruzada y que aquí
   aplica sobre todo a la Fase 5: si un widget del mockup no tiene fuente real en el EDW, se
   declara fuera de alcance en este documento, **no se implementa con datos falsos**.
3. **Rollback por variable de entorno**, mismo patrón ya establecido (`COMISION_MODO`,
   `CARTERA360_RUTA_INTELIGENTE_ENABLED`).
4. No se tocan los módulos transaccionales de Comisiones ni de Cartera para construir el
   dashboard nuevo (decisión del usuario): el dashboard **lee**, no reimplementa.
5. Reporte de auditoría **antes** de modificar código (flujo de `CLAUDE.md` §Flujo de trabajo).

---

## Fase 0 — Auditoría previa (bloqueante)

Producir `docs/auditoria/43_correcciones_sesion_ventas_y_datos.md` con el formato estándar
(fecha, alcance, método, hallazgos con severidad, evidencia, consultas literales, impacto,
riesgo, recomendación). Las hipótesis de las Fases 1-5 de este plan son **hipótesis**: cada una
se confirma o se refuta con evidencia antes de escribir una línea de código.

**Bloqueante de entorno:** en el momento de redactar este plan `docker ps` no devolvió ningún
contenedor — `bi_postgres_edw` y `bi_backend` estaban apagados. Toda la validación en vivo de las
Fases 0-1 requiere levantarlos (`docker compose up -d postgres_edw backend`). Las consultas de
reconciliación quedan escritas abajo, marcadas **Pendiente de validar**.

---

## Fase 1 — R1: el reporte de productos sin movimiento no concuerda con Producción

> *"el informe de productos sin movimientos en los almacenes no concuerdan los datos con el edw
> con la bd de produccion, revisar en que momento me faltan datos"*

### Alcance

- `backend/app/repositories/warehouse_repository.py::get_articulos_sin_venta` (líneas 290-400)
- `backend/app/services/warehouse_service.py::get_reporte_sin_venta`
- `etl/extractors/kardex_extractor.sql` → `edw.fact_movimientos_inventario`
- `etl/transformers/fact_transformer.py::transformar_movimientos_inventario`
- `etl/orchestrator.py` `PIPELINE_CONFIG` (línea 277, loader `fact_inc`, `delta_col='fecdoc'`)

### Hipótesis con evidencia estática (a confirmar en Fase 0)

| ID | Hipótesis | Evidencia estática | Severidad esperada |
|---|---|---|---|
| **H43-1** | **Ventana de historia truncada.** `.env` fija `FECHA_DESDE=2020-01-01` y el extractor filtra `fecdoc >= '{FECHA_DESDE}'`. El EDW **no tiene** kardex anterior a 2020, y no existe fila de saldo inicial. | `etl/extractors/kardex_extractor.sql:24`, `.env:38` | **Alta** |
| **H43-2** | **`stock_actual` del reporte no es la existencia real.** El reporte calcula stock sumando el kardex completo disponible (`SUM(entrada) - SUM(salida)`), pero ese "completo" empieza en 2020 (H43-1). Producción reporta `articulos.exiact` / `vi_mv_existencias`, que incorpora todo el histórico previo. La diferencia es exactamente el saldo al 2019-12-31 de cada `(codart, codalm)`. | `warehouse_repository.py:342-349`; regla de negocio 6 | **Alta** |
| **H43-3** | **Faltan filas por universo restringido.** El universo del reporte es `SELECT DISTINCT producto_sk, almacen_sk FROM fact_movimientos_inventario` — un artículo que **existe en la bodega pero cuyo último movimiento es anterior a 2020** no aparece en el reporte, aunque en Producción es el caso más extremo de "sin movimiento". Es el mismo patrón del hallazgo H-2 ya corregido en Fase 6.1 (el peor caso era el único invisible). | `warehouse_repository.py:334-341` | **Alta** |
| **H43-4** | **`fecha_ultima_venta` sesgada.** Si la última venta real es previa a la ventana, el reporte devuelve `NULL` ("nunca se vendió") en lugar de la fecha real. Es un dato distinto de "no hay dato". | `warehouse_repository.py:350-359` | Media |
| **H43-5** | **Sin filtro de estado de documento (H-8 heredado).** `kardex_extractor.sql` es el único extractor que **no** aplica el token `{ESTADO}` — facturas anuladas (`'A'`) cuentan como venta y como movimiento. Un artículo cuya única "venta" fue anulada se clasifica como *con* movimiento. Ya documentado, nunca corregido. | `kardex_extractor.sql` (ausencia de `{ESTADO}`) vs. resto de extractores | Media-Alta |
| **H43-6** | **Exclusión silenciosa de `Z-9001`.** `EXCLUIR_CODART = {"Z-9001"}` se definió para el modelo de demanda; verificar si `_filtros_snapshot` lo aplica también a este reporte y si el usuario espera verlo. | `warehouse_repository.py:24` | Baja |
| **H43-7** | **Cardinalidad SCD2.** El reporte agrupa por `codart` para colapsar versiones SCD2, pero el `JOIN` a `dim_producto` en el universo se hace por `producto_sk` — dos versiones vigentes del mismo artículo (violación de SCD2) partirían la fila. | `warehouse_repository.py:336-337, 371-382` | Media |

### Validaciones obligatorias (SQL a ejecutar en Fase 0)

Todas con **el mismo recorte** en ambos lados (`codemp='01'`, mismo rango de fechas, mismo almacén):

1. **Pérdida de registros / ventana:**
   `SELECT MIN(d.fecha_completa), MAX(d.fecha_completa), COUNT(*) FROM edw.fact_movimientos_inventario m JOIN edw.dim_fecha d ON m.fecha_sk=d.fecha_sk;`
   contra `SELECT MIN(fecdoc), MAX(fecdoc), COUNT(*) FROM kardex WHERE codemp='01';` (SAP, SELECT puro).
   Confirma/refuta H43-1 y cuantifica cuántas filas quedaron fuera.
2. **Stock:** para una muestra de 20 `(codart, codalm)` con stock alto, comparar
   `SUM(CASE WHEN es_entrada … END)` del EDW contra `vi_mv_existencias` del ERP. Confirma H43-2 y
   mide la magnitud de la diferencia (¿es constante por artículo = saldo inicial faltante?).
3. **Universo:** contar `(codart, codalm)` con existencia > 0 en `vi_mv_existencias` que **no**
   aparecen en `SELECT DISTINCT producto_sk, almacen_sk FROM fact_movimientos_inventario`.
   Confirma H43-3 y cuantifica las filas ausentes del reporte.
4. **Estado:** `SELECT COUNT(*) FROM kardex k JOIN <cabecera> e ON … WHERE e.estado='A' AND k.tiporg='FAC'`
   (SAP) para dimensionar H43-5.
5. **Aislar la etapa** (paso 3 del flujo del auditor): medir el mismo conteo en (a) el resultado
   del extractor, (b) el DataFrame post-transformer, (c) la tabla cargada. La diferencia dice si
   la pérdida la introduce la extracción, la transformación o la carga.
6. Las 8 validaciones automáticas mínimas de la skill `etl-edw-auditor` sobre
   `fact_movimientos_inventario` (duplicados, huérfanas, % de FKs en el centinela `-1`, fechas
   fuera de rango, SCD2), reportando también las que salgan limpias.

### Correcciones candidatas (se eligen tras la Fase 0, según qué hipótesis se confirme)

- **Si H43-1/H43-2/H43-3 se confirman (lo más probable):** decisión del usuario entre dos vías:
  - **Vía A — recarga histórica completa:** bajar `FECHA_DESDE` a la primera fecha real de
    `kardex` y re-ejecutar la carga de `fact_movimientos_inventario` (append-only idempotente por
    fecha, ya soportado). Corrige las cuatro hipótesis de raíz. Costo: una corrida ETL larga.
  - **Vía B — hecho de saldo inicial:** extractor nuevo que materialice el saldo por
    `(codart, codalm)` al `FECHA_DESDE - 1` y lo cargue como fila de apertura. Más barato en
    tiempo de carga, agrega una tabla/convención nueva al modelo.
  - Vía A es la recomendada: no introduce un objeto nuevo al modelo dimensional y deja el kardex
    reconciliable 1:1 contra el ERP, que es el objetivo declarado del requerimiento.
- **Si H43-3 se confirma:** ampliar el universo del reporte a **el catálogo de existencias**, no
  solo a las combinaciones con movimiento, para que "nunca se movió" sea un caso representable.
- **Si H43-5 se confirma:** agregar el token `{ESTADO}` / columna de estado al extractor de
  kardex. Es cambio de ETL + re-extracción (mismo alcance de la Vía A, conviene hacerlos juntos).
- **En todos los casos:** declarar en el propio reporte (contrato `ReporteBodegaResponse`,
  sección de filtros aplicados) **la ventana real de datos disponible** y la fuente del stock, en
  vez de servir un número silenciosamente distinto al del ERP.

### Validación de cierre

Re-ejecutar las consultas 1-3 y adjuntar el antes/después al reporte 43; `edw/06_verificacion.sql`;
`pytest backend/tests/unit` + `backend/tests/integration/test_warehouse_actualizacion_bodega.py`.

---

## Fase 2 — R2: al cerrar sesión queda rastro del usuario anterior

> *"al cerrar session quitar por completo el rastro de tokens o acciones que haya hecho un
> usuario, ya que se estan quedando los cambios que hizo un usuario y se visualiza si se loguea
> con otro usuario"*

### Hallazgos (confirmados por lectura de código, no hipótesis)

| ID | Hallazgo | Evidencia |
|---|---|---|
| **H43-8** | **La caché de TanStack Query nunca se limpia al cerrar sesión.** `logout()` solo borra `auth_token`/`auth_user` de `localStorage` y hace `navigate('/login')` — una navegación SPA, **sin recarga de página**. El `QueryClient` es un singleton creado en `providers.tsx` y sobrevive intacto: al entrar el usuario B, cada `useQuery` sirve primero el dato cacheado del usuario A (KPIs, cartera, comisiones, nombres de clientes = PII) hasta que el refetch responda. **Es el mecanismo exacto del síntoma reportado.** | `frontend/src/store/authStore.ts:29-33`, `frontend/src/components/layout/UserMenu.tsx:38-41`, `frontend/src/app/providers.tsx:4` | **Alta** |
| **H43-9** | **Estado Zustand en memoria sobrevive al logout.** `crossSellStore` (cliente seleccionado, PII), `rutaVentasStore` (`clienteAbiertoId`), `toastStore` no se resetean. Sin recarga de página persisten en el siguiente login. | `frontend/src/store/*.ts` | Media |
| **H43-10** | **`sessionStorage` con filtros persiste entre usuarios.** `bodega-filters` se guarda en `sessionStorage`, que **no** se limpia al hacer logout ni al cambiar de usuario — solo al cerrar la pestaña. El usuario B ve la bodega/categoría/rango que dejó filtrado el usuario A. Con la RLS por almacén (RN-B10) esto además produce un filtro vacío inexplicable si B no tiene acceso a esa bodega. | `frontend/src/store/bodegaFiltersStore.ts:36-39` | Media |
| **H43-11** | **`ui_sidebar_collapsed` en `localStorage`** sobrevive (preferencia de UI, impacto cosmético). | `frontend/src/store/uiStore.ts:20` | Baja |
| **H43-12** | **No existe logout del lado del servidor.** `backend/app/api/routes/auth.py` solo expone `POST /login`. El JWT emitido sigue siendo **válido hasta su expiración** aunque el usuario "cerró sesión": un token copiado antes del logout sigue autenticando. El requerimiento pide literalmente "quitar por completo el rastro de tokens". | `backend/app/api/routes/auth.py` | **Alta** |

### Trabajo

1. **Un solo punto dueño del cierre de sesión.** Nueva función `cerrarSesion()` (p. ej.
   `frontend/src/services/session.ts`) que ejecuta, en orden: `POST /auth/logout` (best-effort,
   no bloquea si falla) → `queryClient.clear()` → reset de todos los stores Zustand →
   `sessionStorage.clear()` → limpieza de las claves de `localStorage` de la app →
   `authStore.logout()`. `UserMenu` y el interceptor 401 de `http.ts` llaman **a esta única
   función**, nunca a `logout()` directo (hoy el interceptor duplica la limpieza a mano y también
   deja la caché intacta).
2. **Reset explícito por store**, no borrado global a ciegas: cada store expone `reset()` y la
   función de cierre los invoca. Evita el efecto colateral de borrar claves de terceros.
3. **`POST /auth/logout` real en el backend.** Denylist de `jti` con expiración natural (tabla
   `public.tokens_revocados` vía migración Alembic nueva, mismo patrón append-only de
   `comision_config_auditoria` / `ml_model_runs`; o Redis si se decide agregar la dependencia —
   **decisión pendiente del usuario**, la vía Alembic es la recomendada por no sumar
   infraestructura). Requiere emitir `jti` en el token (`core/security.py`) y verificarlo en la
   dependencia de autenticación. Registrar el evento en el log de auditoría existente.
4. **Defensa en profundidad:** clave de caché de React Query prefijada con el `id` de usuario, de
   modo que aunque quedara un residuo nunca calce con otro usuario.

### Validación

- Test de integración: login A → `GET /me` con su token → `POST /auth/logout` → **el mismo token
  debe devolver 401**.
- Test de frontend/manual reproducible: login A, cargar Bodega + Ruta, logout, login B **en la
  misma pestaña sin recargar** → ningún dato de A visible en ningún panel; `sessionStorage` vacío.
- `tsc --noEmit` + `oxlint` limpios; `pytest backend/tests/unit` y `integration` sin regresiones.

---

## Fase 3 — R3: "Próximas acciones" no funciona + documentarlo en el manual

> *"revisar exactamente como es que se estan registrando Próximas acciones, ya que no funciona y
> eso explicar como funciona en el manual de usuario"*

### Hallazgo raíz (confirmado, no hipótesis)

**H43-13 (Alta) — El panel y su fuente de datos se excluyen mutuamente.**

- El registro **sí funciona**: `QuickLogForm` envía `proxima_accion_fecha` → `POST /ruta/gestion`
  → `GestionService.registrar_gestion` valida el formato ISO → `log_gestion` persiste la columna
  en `public.gestion_cartera_eventos`. La escritura está correcta de punta a punta.
- El panel **no puede mostrarla nunca**: `UpcomingActions` no llama a ningún endpoint; filtra
  `proxima_accion_fecha` sobre `data.clientes` de `GET /ruta/hoy`
  (`UpcomingActions.tsx:17-19`, `VentasRuta.tsx:58`).
- Pero `Cartera360Service.get_ruta_hoy` **descarta explícitamente** del top-N a todo cliente con
  `proxima_accion_fecha` en el futuro (`cartera360_service.py:188-189`, `_elegible_hoy`).
- Consecuencia: la lista que alimenta el panel es exactamente el complemento de lo que el panel
  debe mostrar. Sobrevive solo un caso degenerado (fecha **vencida** en un cliente que además
  entra al top-N y no fue gestionado hoy), que ni siquiera es una acción "próxima".
- La exclusión del ranking es **correcta y deliberada** (rotación de la ruta) y el manual ya la
  describe (`docs/manual_ruta_inteligente_ventas.md:61-63` promete que esos clientes "los
  encuentras en el panel Próximas acciones §1.7"). **El manual describe el comportamiento
  correcto; el código nunca lo implementó.** No hay que revertir la exclusión: falta la fuente.

### Trabajo

1. **Endpoint nuevo `GET /analytics/ventas/ruta/proximas-acciones`** — agenda propia del vendedor
   autenticado, independiente del top-N del día. Fuente: `public.gestion_cartera_eventos`,
   última gestión por cliente con `proxima_accion_fecha IS NOT NULL`, resuelta a
   `id_cliente_transaccional` vía `cliente_lookup` (misma resolución que
   `get_ultima_gestion_por_cliente_ids`), ordenada por fecha ascendente.
   - **RLS obligatoria** (riesgo R-3 del plan de Ruta, sin excepción): self-scope al `codven` del
     usuario, mismo `_requerir_vendedor` del resto del router.
   - Devolver `vencida | hoy | proxima` derivado de la fecha, para que la UI distinga una promesa
     incumplida de una agendada — hoy no hay forma de verlo.
2. **`UpcomingActions` consume el endpoint nuevo** (hook propio) en vez de derivar de `/ruta/hoy`;
   conserva el estado vacío real y el clic que abre el drawer del cliente.
3. **Cerrar el ciclo:** al registrar una gestión, invalidar la query de próximas acciones (ya se
   invalida `/ruta/hoy`), para que la acción aparezca en el panel inmediatamente — hoy el usuario
   registra una fecha y no ve ningún efecto, que es exactamente el "no funciona" reportado.
4. **Manual de usuario** (`docs/manual_ruta_inteligente_ventas.md`): reescribir §1.7 explicando
   el ciclo completo y verificado — dónde se captura la fecha (campo "Próxima acción" del
   formulario de gestión), qué pasa con el cliente en la ruta del día (sale del ranking hasta esa
   fecha, y por qué), dónde reaparece, qué significa vencida/hoy/próxima, y qué **no** hace
   (no envía recordatorio ni notificación — declararlo explícitamente si sigue siendo el caso).
   Ajustar también §1.3 (tabla de campos) y la sección de endpoints con el endpoint nuevo.

### Validación

Test de integración: registrar gestión con fecha futura → el cliente **desaparece** de
`/ruta/hoy` y **aparece** en `/ruta/proximas-acciones`; un vendedor ajeno recibe 403;
fecha vencida se etiqueta como tal.

---

## Fase 4 — R4: activar Comisiones Variables y corregir el panel de Ventas

> *"APROVAR LAS METAS Y COMISIONES POR VARIBLES PARA METER EN FUNCIONAMIENTO Y CORREGIR EL PANEL
> DE VENTAS"*

Esta fase mueve **dinero real**. Nada aquí se aplica sin las verificaciones previas.

### 4.1 Verificaciones previas bloqueantes (antes de cambiar `COMISION_MODO`)

El estado actual es `COMISION_MODO=plana` (default de `config.py:178`; la variable **no está en
`.env`**). El plan original (`plan_integracion_comisiones_variables.md` §Fases) exige pasar por
`sombra` antes de `variable`. Antes de activar:

1. **Salvaguarda 2 — líneas sin costo:** `GET /gerencia/goals/lineas-sin-costo` debe estar
   cuantificado. Con `costo_promedio ≈ 0` el margen se infla al ~100% del precio (hallazgo ya
   documentado en Venta Cruzada Fase 4 y en `39_madurez_bi_toma_decisiones.md`): **con
   `COMISION_MODO=variable` eso se convierte en pago sobre un margen falso.** Bloqueante duro.
2. **Matriz de categorías y factores de crédito vigentes** cargados y aprobados por gerencia
   (`/commission-config/matriz`, `/credito`, `/vendedores/{codven}`).
3. **Piloto en sombra con al menos un mes cerrado**, revisando la alerta de divergencia
   (`NotificationService._generar_divergencia_comisiones`, activa solo en `sombra`) y el panel
   `CommissionSimulationPanel`.
4. **Los 3 valores de `COMISION_MODO` arrancan el sistema** (pendiente declarado en
   `plan_correcciones_pendientes.md` §71.3 — los tests cubren la lógica, no el arranque).
5. Verificar la desalineación de datos semilla ya detectada en B-3: `ventas_gye@empresa.com` tiene
   un `id_vendedor_origen` inexistente en el EDW. Un vendedor sin `codven` válido no cobra nada
   bajo ningún esquema.

### 4.2 Activación (secuencia, con rollback en cada paso)

`plana` → **`sombra`** (declarar en `.env`, `docker compose up -d backend` — un `docker restart`
no relee `env_file`) → cierre y revisión de un período → **`variable`**.
Rollback en cualquier punto: revertir la variable y reiniciar. Los snapshots oficiales de
`comision_liquidaciones` son inmutables por diseño (RN-CM6): una vez en `variable`, un período
cerrado no se recalcula aunque se cambie la configuración.

### 4.3 Aprobación de metas

`PUT /gerencia/goals/{goal_id}/review` y `GoalsConsole.tsx` ya implementan Aprobar/Rechazar/
Modificar con simulación previa. Verificar sobre datos reales que: el KPI company-wide
(`get_cumplimiento_meta_periodo`) solo agrega metas en estado `APROBADA`; una meta no aprobada no
paga comisión; y el drawer de desglose IQR abre para todos los vendedores del período.
**Trabajo real esperado aquí: validación + corrección de lo que falle, no reconstrucción.**

### 4.4 Corrección del panel de Ventas (parte del mismo requerimiento)

- `VendorGoalDashboard.tsx` ya muestra el dual sombra/variable con el badge "no es lo que se
  paga". Al pasar a `variable` ese texto queda **falso** — el badge debe leerse desde el modo real
  que reporta el backend, no estar hardcodeado a la narrativa del piloto. Verificar y corregir.
- Confirmar que `mi-comision` devuelve `desglose_variable` completo para el vendedor autenticado y
  que el frontend lo renderiza sin asumir campos no nulos (M-4).
- El resto del panel de Ventas se aborda en la Fase 5.

---

## Fase 5 — R5/R6: Dashboard "Mi Negocio" del vendedor

> *"dashboard del perfil de ventas no tiene nada"* + mockup detallado del usuario.

### Diagnóstico del estado actual

`DashboardVentas.tsx` (ruta `/ventas`, la página de aterrizaje del rol) tiene 4 KPI cards de
metas + un buscador de cliente por ID. **Para un vendedor real está efectivamente vacío:**

- Los 3 paneles de análisis (segmento RFM, churn, recomendaciones) **solo aparecen tras escribir
  un `cliente_id` exacto** (`{clienteId && …}`, línea 142) — sin autocompletar, el vendedor tendría
  que saber el código de memoria. En la práctica nunca se renderizan.
- Las 4 KPI cards dependen de `GET /analytics/ventas/goals`; con el desalineamiento de
  `id_vendedor_origen` de B-3 devuelven ceros/guiones.
- Todo el valor real del módulo vive en otras páginas (Mi Meta y Comisión, Venta Cruzada, Mi Ruta
  Inteligente). La página principal del rol no es un dashboard, es un formulario de búsqueda.

### Mapeo del mockup a fuentes reales (invariante 2)

**Implementable con datos reales existentes:**

| Widget del mockup | Fuente real | Nota |
|---|---|---|
| Cuota vs Realizado + barra de progreso | `GET /analytics/ventas/goals` (`meta_mensual`, `cumplimiento_actual`) | Ya existe |
| Meta diaria / falta para hoy | `Cartera360Repository.get_meta_mensual_vendedor` + `get_ventas_dia` | Ya existen, hoy solo los usa la Ruta |
| Ranking (#N de M) | `ranking_vendedores` de `VentasGoalsTracking` | Ya existe, hoy no se muestra en esta página |
| Próximo pago de comisión | `GET /analytics/ventas/goals/mi-comision` (resumen) | Solo lectura, no toca el módulo |
| Evolución mensual (real vs meta) | `metas_comerciales_operativas` + `fact_ventas_detalle` por vendedor/mes | Requiere query nueva, grano ya existente |
| Productos más vendidos por el vendedor | `fact_ventas_detalle` filtrado por `vendedor_sk` | Requiere query nueva de repositorio |
| Clientes en riesgo | `churn_rf` vía `Cartera360Service.get_lista_trabajo` / ruta | Ya existe |
| Próximas actividades / agenda | Endpoint de la **Fase 3** | Dependencia directa |
| "Pipeline" caliente / tibio / frío | Ruta priorizada (score + `probabilidad_recompra` = `100 - churn`) | **Debe etiquetarse "probabilidad de recompra estimada por el modelo", nunca "probabilidad de cierre"** — no hay CRM ni etapas de oportunidad en el ERP |
| Comparativo vs. mes pasado | Mismo histórico de venta por vendedor | Query nueva |
| Drill-down en modal | Drawer de cliente ya existente en la Ruta | Reutilizar |

**No implementable con datos reales — fuera de alcance, se declara aquí en vez de simularse:**

- **Embudo de oportunidades con montos y % de probabilidad de cierre** ($15k @ 90%): no existe
  entidad "oportunidad" en SAP ni en el EDW. Se sustituye por la ruta priorizada real (arriba).
- **Ciclo promedio de venta (22 días)**: solo derivable de gestiones registradas
  (`tiempo_promedio_cierre_dias` de Efectividad Comercial), que exige volumen mínimo
  (`CARTERA360_MIN_GESTIONES_EFECTIVIDAD`); mientras no lo haya, estado vacío real, nunca un número.
- **Insignias / gamificación** ("Rayo", "El Persuasivo"): no hay fuente de eventos ni reglas
  definidas. Requeriría un módulo propio — se propone como fase futura, no en este plan.
- **Feed de noticias de la empresa**: no hay tabla ni proceso de publicación. Fuera de alcance.
- **"Reclamo sin resolver 72h"**: no hay módulo de reclamos en el EDW.

### Trabajo

1. Endpoint agregador `GET /analytics/ventas/mi-negocio` (una llamada, no N) que componga lo
   anterior desde servicios y repositorios ya existentes — mismo patrón de composición por
   inyección de `CrossSellEngineService`/`Cartera360Service`; **sin lógica de negocio nueva de
   comisiones ni de cartera** (invariante 4).
2. Reescritura de `DashboardVentas.tsx` con las 4 filas del mockup, en las capas propuestas por el
   usuario (scoreboard → prioridades del día + agenda → tendencias → resumen).
3. Reemplazar el buscador por ID por el `Autocomplete<T>` ya existente (usado en Venta Cruzada),
   y mover el análisis individual de cliente al drawer, no a un bloque condicional invisible.
4. Filtros de período con 3 botones grandes (Semana / Mes / Trimestre) y selector "Mi meta" vs
   "Meta del equipo", según el mockup.
5. Estados vacíos reales por widget (nunca ceros inventados) y skeletons por sección.
6. Usar `frontend-design` para la dirección visual y `dataviz` **antes** de escribir cualquier
   gráfico (evolución mensual, top productos, medidores).

### Validación

`tsc --noEmit` + `oxlint`; `pytest` unit + integration del endpoint nuevo (incluido un test de RLS:
un vendedor no ve datos de otro); prueba en vivo con un `codven` real del EDW (p. ej. `VEN02`,
usado como control en B-3) contra `bi_backend` reconstruido, comparando cada KPI con una consulta
SQL manual — mismo criterio de verificación que las fases anteriores del proyecto.

---

## Orden de ejecución y dependencias

```
Fase 0 (auditoría 43)  ─┬─> Fase 1 (datos Bodega)      [independiente]
                        ├─> Fase 2 (higiene de sesión)  [independiente, entrega rápida]
                        ├─> Fase 3 (próximas acciones) ──┐
                        ├─> Fase 4 (comisiones variables)│
                        └────────────────────────────────┴─> Fase 5 (dashboard del vendedor)
```

- **Fase 2 primero en entregar valor** (bug de privacidad/PII entre usuarios, corrección acotada).
- **Fase 5 depende de la 3** (widget de agenda) y se beneficia de la 4 (widget de comisión).
- **Fase 1 es independiente** y la más costosa si se elige la Vía A (recarga histórica).

## Riesgos y rollback

| Riesgo | Mitigación |
|---|---|
| Recarga histórica del kardex (Fase 1) altera cifras ya publicadas | Carga append-only idempotente por fecha; ejecutar primero en un volumen de prueba y adjuntar el diff de conteos al reporte 43 |
| Denylist de tokens (Fase 2) rompe sesiones activas | Solo revoca en logout explícito; expiración natural de las filas; rollback = no verificar el `jti` |
| Pago incorrecto al pasar a `COMISION_MODO=variable` | Bloqueante de líneas sin costo; paso obligatorio por `sombra`; rollback = una env var |
| Dashboard nuevo (Fase 5) muestra métricas sin base real | Invariante 2 + tabla de "no implementable" ya declarada arriba |

## Criterios de aceptación

1. El reporte de productos sin movimiento reconcilia contra Producción, o declara explícitamente
   la ventana de datos y la fuente de stock, con el diff cuantificado en la auditoría 43.
2. Tras cerrar sesión e iniciar con otro usuario **en la misma pestaña**, no queda ningún dato,
   filtro ni token del usuario anterior; el token previo devuelve 401.
3. Una "próxima acción" registrada aparece en su panel inmediatamente, y el manual explica el
   ciclo completo verificado contra el código.
4. Comisiones Variables operando en el modo acordado, con las salvaguardas verificadas y el panel
   de Ventas mostrando el modo real vigente.
5. `/ventas` deja de estar vacío: cada widget del dashboard tiene fuente real trazable, y lo que
   no la tiene está declarado como fuera de alcance en este documento.
