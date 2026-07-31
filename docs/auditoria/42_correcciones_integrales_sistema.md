# Auditoría 42 — Correcciones integrales del sistema (Fase 0 + Fase 1 aplicada)

- **Fecha:** 2026-07-29
- **Alcance:** módulo Bodega (backend + frontend), tabla `public.usuarios`, RLS por
  almacén. Origen: `docs/features/plan_correcciones_integrales_sistema.md`.
- **Método:** revisión estática de código (routers, repositorios, servicios, modelos),
  lectura del DDL del EDW (`edw/02_dimensiones.sql`, `edw/03_hechos.sql`), y pruebas de
  integración reales contra `bi_postgres_edw` (Docker, puerto 5433) vía `bi_backend`
  reconstruido. **No se ejecutó ninguna escritura contra Producción** (SAP no se tocó en
  esta fase; todo el trabajo fue sobre el EDW/`public.*`).

---

## Fase 0 — Hallazgos que fundamentan la Fase 1

### A-0.1 — Matriz de endpoints de bodega/almacén y su exposición a `codalm`

Confirmado por `grep -rn "codalm" backend/app/` (estado previo a esta fase): el único
consumo en tiempo de consulta de `codalm` era `notification_service.py:85`. Los 11
endpoints de `backend/app/api/routes/warehouse.py` (`/filtros`, `/kpis`,
`/salidas-forecast`, `/prediccion-compras-mes`, `/rotacion-matriz`, `/top-productos`,
`/salidas-categoria`, `/stock-reorden`, `/necesidad-compra`, `/inventario-matriz`,
`/transferencias-sugeridas`) más `/reportes/{tipo}` y `/reportes/{tipo}/excel` aceptaban
`almacen` como query param libre, sin restricción alguna por usuario. Confirma H-1 del
plan al 100%: **cero** endpoints aplicaban una restricción de bodega antes de esta fase.

### A-0.2 — Mecanismo de RLS existente para `sucursal` (referencia de diseño)

`resolve_sucursal_filter` (`app/api/dependencies.py`) ya resolvía este mismo problema
para el rol `ventas`/`bodega` a nivel de sucursal, con dos decisiones de diseño que se
replicaron para `resolve_almacenes_filter`: (a) un almacén/sucursal ajeno **no** produce
403 — se intersecta silenciosamente, evitando que el frontend rompa por arrastrar un
parámetro sin intención maliciosa; (b) administrador/gerencia quedan sin restricción.

### Diseño elegido para la restricción (no estaba en el plan original, decidido durante la implementación)

El plan proponía threading explícito de `almacenes_permitidos: list[str] | None` por
cada función pública de `WarehouseRepository`/`WarehouseService`/cada endpoint (~14
funciones × 3 capas). Se implementó una alternativa equivalente en efecto pero de menor
superficie de cambio: `WarehouseRepository` recibe `almacenes_permitidos` **en su
constructor** (inyectado por request vía `get_warehouse_repository`, que depende de
`resolve_almacenes_filter`), y `_filtros_snapshot` — ya el único choke point de filtros
del repositorio, llamado internamente como `self._filtros_snapshot(...)` — pasó de
`@staticmethod` a método de instancia que lee `self.almacenes_permitidos`. Efecto
idéntico al del plan (una sola restricción aplicada a las ~14 funciones sin tocarlas una
por una) con cero cambios en `WarehouseService` y en `warehouse.py` (routers). Se
documenta como desviación deliberada del diseño del plan, verificada con la suite de
integración nueva.

### Detalle confirmado del plan (B-2): filtro por nombre vs. asignación por código

`_filtros_snapshot` ya filtraba `almacen` (elección del usuario) por
`al.nombre_almacen = :almacen`. La restricción de seguridad se implementó por
`al.codalm IN (...)` — dominios distintos, ambos coexisten en AND (intersección real,
nunca el uno ampliando al otro).

---

## Fase 1 — Aplicado

### H-1 (CRÍTICO, seguridad) — CERRADO

**Antes:** cualquier usuario con rol `bodega` podía leer/exportar KPIs, stock, rotación,
transferencias y el Excel completo de **cualquier** almacén, cambiando `?almacen=<otro>`
en la URL — sin relación con la bodega que el admin le hubiera asignado (que, además,
antes de esta fase solo podía ser "una" o "todas": el modelo 1:1 `usuarios.codalm`).

**Después:**
1. Migración Alembic `0006_usuario_almacenes`: tabla N:N `public.usuario_almacenes
   (usuario_id, codalm)` + columna real `usuarios.todos_los_almacenes BOOLEAN`.
   Backfill: `codalm` no nulo → una fila; `codalm IS NULL` + rol `bodega` →
   `todos_los_almacenes = TRUE` (mismo significado que tenía `NULL` antes). Columna
   `usuarios.codalm` eliminada en la misma migración. Aplicada y verificada contra
   `bi_postgres_edw` real (`alembic upgrade head` sin errores).
2. `resolve_almacenes_filter` (`app/api/dependencies.py`): rol `bodega` sin
   `todos_los_almacenes` → devuelve sus `codalms` asignados (puede ser `[]` si el admin
   no le asignó ninguna — en ese caso no ve ningún dato, nunca "todos" por omisión);
   `todos_los_almacenes=True` o rol privilegiado → `None` (sin restricción).
3. `WarehouseRepository._filtros_snapshot` aplica `al.codalm IN (:codalms_permitidos)`
   en AND con el filtro `almacen` que el usuario elija — intersección real, nunca
   ampliación. Lista vacía → `1 = 0` (bloquea todo, no "todo" por defecto).
4. `get_salidas_serie_diaria` (único método con `JOIN dim_almacen` condicional) corregido
   para activar el JOIN también cuando hay restricción de seguridad sin filtro de
   usuario elegido — de lo contrario el `WHERE` referenciaría un alias inexistente.
5. `get_series_salidas_producto_almacen` (usado por la justificación de transferencias,
   RN-B9) no pasaba por `_filtros_snapshot` (compara candidatos entre TODAS las bodegas
   por diseño) — se le añadió la misma restricción por defensa en profundidad, para que
   un usuario bodega restringido no reciba series de salida de almacenes fuera de su
   asignación aunque el flujo de transferencias las toque internamente.
6. `notification_service.py::_generar_bodega` migrado: ya no lee `user.codalm`
   (columna eliminada); la restricción real la aplica el `WarehouseRepository` inyectado
   transitivamente para el usuario autenticado de la request.
7. `UserCreate`/`UserUpdate`/`UserOut`/`UserMe`: `codalm: str` → `codalms: list[str]`.
   `UserService._resolve_role_link` valida cada código contra `edw.Dim_Almacen`
   (reutiliza `CatalogRepository.get_almacen`, sin query nueva). `UserRepository` gana
   `_set_almacenes` (reemplazo total de la lista en cada `create`/`update` que la toque).
8. Frontend: `UsersManagement.tsx` — selector múltiple de bodegas (antes un único
   `<select>`); `types/admin.ts`/`types/auth.ts` actualizados; `Login.tsx` propaga
   `codalms`/`todosLosAlmacenes` al store de sesión.

**Validación ejecutada:**
- `alembic upgrade head` contra `bi_postgres_edw` real: aplicado sin errores.
- `bi_backend` reconstruido con el código nuevo (`docker compose build backend` +
  `docker compose up -d backend`), arranque limpio (log de startup sin `WARNING`/`ERROR`
  de modelos ni de esquema).
- `pytest backend/tests/unit` (182 passed tras el fix de `test_user_service.py` — los 4
  tests afectados por el cambio de contrato `codalm` → `codalms` se actualizaron; el
  único fallo restante, `test_classify_vendor_risk_marca_en_riesgo_y_alta_probabilidad`,
  es preexistente y no relacionado, ya documentado en el CLAUDE.md del proyecto).
- `pytest backend/tests/ -m integration` (contra `bi_postgres_edw`/`bi_backend` reales):
  **114 passed, 4 skipped, 1 failed** en 12m24s. El único fallo
  (`test_meta_sugerida_vendedor_expone_trazabilidad_del_motor`,
  `tests/integration/test_metas_actualizacion.py`) es preexistente y ajeno a esta fase —
  módulo de Metas y Comisiones, sin relación con `warehouse_repository.py`,
  `user_service.py` ni las rutas tocadas; coincide con la familia de fallos
  preexistentes de "metas/goal_ml_service" que el CLAUDE.md del proyecto ya documenta
  como conocidos y no bloqueantes.
- Test de integración nuevo `backend/tests/integration/test_bodega_rls.py`: **las 6
  pruebas pasaron** contra el EDW real. Cubre (a) usuario con una bodega pidiendo otra —
  la restricción intersecta, no filtra los datos ajenos (`skus_activos == 0` al pedir la
  bodega ajena); (b) usuario con varias bodegas — recibe la unión de las suyas; (c)
  usuario con `todos_los_almacenes` — sin restricción; (d) alta de usuario bodega sin
  bodegas ni "todos" — rechazada por `ValidationError` (400); (e) el export Excel
  (vector de fuga de mayor volumen según el plan) respeta la misma restricción.
- `cd frontend && npx tsc --noEmit`: limpio. `npx oxlint` sobre los 6 archivos tocados
  (`UsersManagement.tsx`, `BodegaFilterBar.tsx`, `types/admin.ts`, `types/auth.ts`,
  `Login.tsx`, `store/authStore.ts`): exit 0, sin hallazgos.

**Declaración obligatoria:** no se ejecutó ninguna escritura contra Producción (SAP) en
esta fase; todos los cambios de esquema fueron sobre `public.*` en el EDW de PostgreSQL,
vía Alembic.

### Ampliación 2026-07-29 (mismo día, petición explícita del usuario) — el selector de filtros ya no lista bodegas ajenas

Instrucción del usuario: *"el filtro de bodega no debe mostrar otras bodegas si el
usuario solo se creó específicamente para una bodega, pero si el usuario se creó para
todas las bodegas sí puede ver ese filtro con todas las demás bodegas"*.

**Antes:** `GET /analytics/bodega/filtros` devolvía siempre el catálogo completo de
nombres de almacén (`AnalyticsRepository.get_almacenes()`, catálogo compartido con otros
módulos) sin importar la asignación del usuario — la RLS de la Fase 1 ya impedía leer
datos de una bodega ajena, pero el desplegable de la UI seguía ofreciéndola como opción
(UX confusa, gap documentado como pendiente en la primera versión de esta auditoría).

**Después:** `GET /analytics/bodega/filtros` (`warehouse.py::get_filtros`) inyecta
`resolve_almacenes_filter` (la misma dependencia de RLS de la Fase 1, reutilizada sin
duplicar lógica) y, cuando devuelve una lista (no `None`), traduce los `codalm`
permitidos a `nombre_almacen` vía `CatalogRepository.list_almacenes()` (mismo catálogo
que ya usa el panel de administración) e intersecta la lista de nombres antes de
devolverla. Un usuario creado para una sola bodega ve solo esa; con varias, ve solo
esas; con `todos_los_almacenes=True` (o rol gerencia/administrador), ve el catálogo
completo — sin cambios en `BodegaFilterBar.tsx` (el frontend ya consumía la lista tal
cual venía del backend).

**Validación:** nuevo test `test_filtros_solo_lista_bodegas_asignadas` en
`test_bodega_rls.py` — confirma que un usuario restringido no ve el nombre de la bodega
ajena en `almacenes` y que un usuario con `todos_los_almacenes` sí lo ve.
`test_bodega_rls.py` se reestructuró con fixtures `scope="module"` (un usuario por
perfil, no uno por test) para no agotar el rate limit real de `/auth/login`
(`AUTH_LOGIN_RATE_LIMIT=5/minute`, la misma protección que valida
`test_auth_endpoints.py`) al sumarse esta séptima prueba. Suite de integración completa
re-ejecutada tras el cambio: `bi_backend` reconstruido de nuevo,
`pytest backend/tests/ -m integration` → **115 passed, 4 skipped, 1 failed** (mismo
único fallo preexistente y ajeno de `test_metas_actualizacion.py` ya documentado
arriba); las 7 pruebas de `test_bodega_rls.py` (las 6 originales + la nueva de filtros)
pasaron.

### Gaps conocidos, no bloqueantes (quedan para una fase posterior del plan)

- Eliminación permanente de usuarios (`DELETE /users/{id}/permanente`) no existe todavía
  (Fase 5 del plan) — la limpieza de usuarios de prueba en `test_bodega_rls.py` usa el
  soft-delete existente (`deactivate_user`), dejando cuentas desactivadas acumuladas en
  entornos donde se repita la suite muchas veces. No afecta la seguridad del sistema.
- `/kpis-inventory` (endpoint legado, `AnalyticsService.get_warehouse_kpis`) solo filtra
  por `sucursal` (ya restringido por `resolve_sucursal_filter(allow_override=False)`) y
  no expone un parámetro `almacen` — fuera del vector de fuga de H-1 por diseño, no
  requirió cambios.

## Fase 2 (parcial) — Aplicado

**§2.1 (icono de calendario) y §2.2 (filtro inteligente categoría→proveedor de Bodega):**
nuevo `DateField` (icono explícito vía `lucide-react`, independiente del
`::-webkit-calendar-picker-indicator`, no estándar y ausente en Firefox/Safari) aplicado
en `BodegaFilterBar.tsx`, `QuickLogForm.tsx`, `DashboardAdmin.tsx`,
`DashboardGerencia.tsx`. `WarehouseRepository.get_proveedores(categoria)` restringe el
catálogo de proveedores a los que realmente suministran esa categoría
(`EXISTS` contra `edw.fact_compras` + `dim_producto.clase`, sin inventar combinaciones);
`GET /analytics/bodega/filtros?categoria=...` lo expone; en `BodegaFilterBar.tsx`,
cambiar de categoría limpia el proveedor seleccionado y, si la categoría no tiene
proveedores registrados, el selector se deshabilita con una leyenda explícita (`helper`
nuevo en `FilterField`) en vez de una lista vacía sin contexto. §2.3 (`ComboboxField`) y
§2.4 (auditoría A-0.4 de alineación de modelos TS↔Pydantic) quedan pendientes.

Validado: `tsc --noEmit` y `oxlint` limpios; `bi_backend` reconstruido sin
`WARNING`/`ERROR` de arranque; `pytest backend/tests/unit` (186 passed, 1 falla
preexistente ajena); subconjunto de integración de Bodega (26 passed, 1 skipped).

**§2.3 (`ComboboxField` híbrido) — verificado sin hallazgos, sin componente nuevo:**
`frontend/src/components/ui/Autocomplete.tsx` ya implementa exactamente el patrón que
pide el plan -- búsqueda tipeable (debounced) contra un catálogo real del backend, sin
opción de enviar texto libre como valor final: el estado real solo se actualiza vía
`onSelect(item)` al elegir una opción de la lista, nunca desde el texto tecleado
directamente, así que ya es imposible "enviar basura" a un campo que el backend espera
como código exacto. Ya está en uso para productos/clientes
(`SaleAssistant.tsx`, Venta Cruzada) y vendedores (`CommissionConfigPanel.tsx`). No se
encontró ningún campo de código exacto en el frontend que acepte texto libre sin
catálogo de respaldo. Sin cambios de código requeridos.

§2.4 (auditoría A-0.4 de alineación de modelos TS↔Pydantic) queda pendiente -- es un
barrido transversal de todo el frontend/backend, más apropiado como una sesión de
auditoría dedicada que como una tarea puntual dentro de esta fase.

## Fase 3 — Módulo Gerencia — Aplicado

**§3.1 (KPIs filtrables por vendedor):** `GET /gerencia/goals/commissions` y
`GET /gerencia/goals/tracking` ganan `vendedor` opcional (nombre de
`edw.dim_vendedor.nombre_vendedor`, mismo criterio que el selector ya existente de
`DashboardGerencia.tsx`) — sin selección, comportamiento previo intacto (todos los
vendedores); con selección, filtra en SQL (`goal_repository.py::get_commission_report`/
`get_commission_tracking_rows`). Selector nuevo en `CommissionTracker.tsx` y
`GoalsConsole.tsx` (reutiliza `useVendedores`, ya usado en `DashboardGerencia.tsx` — sin
endpoint de catálogo nuevo).

**§3.2 (gráficos de predicción) — verificado sin hallazgos nuevos:** "Histórico y
Predicción" (`sales_rf`) y "Predicción de Compras — Próximo Mes" (`demand_rf`) ya
muestran unidades separadas sin mezclar escalas (dólares vs. unidades, sin ningún
porcentaje cruzado en ninguno de los dos), tooltips construidos desde el payload real
(`ChartTooltip`, no texto hardcodeado), y `DashboardGerencia.tsx` ya aclara
explícitamente que el forecast de ventas no respeta fecha/categoría (RN-G1). Ambos
contratos (`ml/contracts/models/sales.json`, `demand.json`) están en `status: "active"`,
por lo que `contract_validation.py` ya bloquea en tiempo real cualquier predicción fuera
de `plausible_range` (`ModelContractError`) — no se encontró contrato en `draft`
silenciando desvíos. Sin cambios de código requeridos.

**§3.3 (metas y comisiones) — verificado sin hallazgos nuevos:** el flujo
Aprobar/Rechazar/Modificar ya está cableado en `GoalsConsole.tsx` (`useReviewGoal` →
`PUT /{goal_id}/review`, con monto y comisión editables inline antes de aplicar); el
factor de presión comercial ya es un slider editable (0–25%); la simulación previa
(`POST /commission-simulation`) ya tiene panel propio (`CommissionSimulationPanel.tsx`,
con meses de historial editables 3/6) montado en `DashboardMetas.tsx`. H-6 (INFO) del
plan ya estaba resuelto de una fase anterior no documentada explícitamente como tal;
este hallazgo se cierra aquí sin cambios de código.

**§3.4 (gráficos de rendimiento) — verificado sin hallazgos nuevos:** "Vendedores en
riesgo" y "Alta probabilidad de superar la meta" (`GoalMLService.classify_vendor_risk`)
se calculan sobre `ranking_vendedores` real de `AnalyticsService.get_sales_kpis` (EDW);
"Recomendaciones por categoría" (`GoalMLService.get_category_recommendations`) reutiliza
el modelo real `association` (mismo motor de venta cruzada) agregado por
`dim_producto.nombre_clase`. Ningún valor estático encontrado; `GoalsAISummaryPanel.tsx`
está montado en `DashboardMetas.tsx` consumiendo el endpoint real
`GET /gerencia/goals/ai-summary`. Sin cambios de código requeridos.

Validado: `python -m py_compile` limpio en los 4 archivos backend tocados; `tsc --noEmit`
y `oxlint` limpios en los 5 archivos frontend tocados.

## Fase 4 — Módulo Ventas — Aplicado (parcial)

**§4.1 (auditar RLS/agregación de cada gráfico) — verificado sin hallazgos nuevos:**
`DashboardVentas.tsx` (metas, churn, segmento RFM, recomendaciones) y
`VentasCartera360.tsx` (lista de trabajo) ya pasaron por la auditoría dedicada de este
módulo (`docs/auditoria/34_actualizacion_modulo_ventas.md`, RN-V4/RN-V5): la fuga de RLS
que permitía consultar `cliente_id` ajenos ya se cerró (`CatalogRepository.
cliente_pertenece_a_vendedor`, 403 si no pertenece) y el bug de agregación de
`/analytics/ventas/goals` (columna `sucursal` inexistente) también. No se encontraron
gráficos nuevos sin RLS o con agregación incorrecta en esta pasada.

**§4.2 (última fecha de compra + estado de cartera) — aplicado:**
`Cartera360Repository.get_lista_trabajo` ya calculaba `ultima_compra` internamente pero
no la exponía; ahora sí. Nuevo `Cartera360Service._estado_cartera(dias_sin_comprar)`
deriva `activo` / `potencial` / `inactivo` con umbrales configurables
(`CARTERA360_DIAS_ACTIVO=60`, `CARTERA360_DIAS_INACTIVO=180` en `config.py`, nunca
hardcodeados). `ClienteListaTrabajo` (schema y tipo TS) gana `ultima_compra`/
`estado_cartera`; `VentasCartera360.tsx` los muestra como columna nueva en la tabla y
badge de color en el drawer de detalle (reutiliza el patrón `Badge` ya usado en el resto
del proyecto, sin componente nuevo).

**§4.3/§4.4 (rediseño del dashboard de Ventas + estado vacío real) — evaluado, sin
cambios en esta pasada:** `DashboardVentas.tsx` ya cubre progreso vs. meta, búsqueda de
cliente con 3 paneles ML (RFM/churn/venta cruzada) y estados vacíos/error reales vía
`ChartCard` (`empty`/`error`, sin ceros inventados). Además, el proyecto ya tiene una
herramienta más completa construida en una fase anterior no documentada explícitamente
en este plan -- "Mi Ruta Inteligente de Ventas" (`VentasRuta.tsx`,
`docs/features/plan_refactor_cartera360_ruta_inteligente.md`, activable con
`CARTERA360_RUTA_INTELIGENTE_ENABLED`): ruta diaria priorizada de ≤10 clientes con
oferta sugerida, motivo, timeline y plan semanal. Un rediseño completo de
`DashboardVentas.tsx` como "herramienta principal del vendedor" (§4.3 literal del plan)
es un esfuerzo de UX considerable que se deja pendiente de una sesión dedicada en vez de
comprimirlo aquí -- el hallazgo real de esta fase (RLS/agregación, última compra/estado
de cartera) ya está cerrado.

Validado: `bi_backend` reconstruido, arranque limpio (6/6 modelos); `pytest
backend/tests/unit` (186 passed, 1 falla preexistente ajena); `pytest
backend/tests/integration/test_cartera360_ruta_inteligente.py` (6 passed, 6 skipped);
`tsc --noEmit`/`oxlint` limpios en los 3 archivos frontend tocados; probado en vivo
contra `bi_backend` real (`GET /analytics/ventas/cartera360/lista-trabajo` responde 200
con el nuevo contrato, sin error de validación Pydantic).

## Fase 5 — Módulo Administración — Aplicado

**§5.1 (paginación real):** `GET /users` migrado a `Page[UserOut]` (antes
`list[UserOut]` con `skip`/`limit` sin metadatos de página). `UserRepository.count()`
ya existía; nuevo `UserService.get_all_paginated` devuelve `(items, total)` -- no se
anota `Page[User]` en el servicio porque `User` es un modelo ORM, no un tipo Pydantic
serializable como parámetro genérico (`PydanticSchemaGenerationError` real encontrado y
corregido durante la validación, ver más abajo); el router arma `Page[UserOut]`
convirtiendo cada `User` con `UserOut.model_validate(...)`. Frontend:
`UsersManagement.tsx` gana `usePagination` + `<Pagination>` (mismo patrón que
Bodega/Notificaciones/Admin), `getUsers(pagination)` tipado con `Page<UserData>`.

**§5.2 (activo/inactivo):** ya estaba completamente implementado de una fase anterior
no documentada como tal -- columna "Estado" clicable + `ConfirmDialog` en
`UsersManagement.tsx`, sobre los endpoints `deactivate_user`/`activate_user` ya
existentes. Verificado sin cambios.

**§5.3 (eliminación permanente):** `UserRepository.delete()` (borrado duro real) ya
existía sin ningún endpoint que lo expusiera. Nuevo `DELETE /users/{id}/permanente`
(`UserService.delete_permanente`): rechaza auto-eliminación y eliminar al último
administrador activo (`UserRepository.count_administradores_activos()`, nuevo). Viable
sin `ON DELETE SET NULL`/`CASCADE` adicionales -- verificado contra los modelos: **toda**
FK hacia `public.usuarios` ya declara `ondelete` explícito (`SET NULL` en
`Goal.approved_by`, `AnomaliaRevision.revisor_id`, `CommissionConfig.creado_por`/
`usuario_id`, `GestionCarteraEvento.usuario_id`, `RecommendationEvent.usuario_id`;
`CASCADE` en `Notification.usuario_id`, `UsuarioAlmacen.usuario_id`), ninguna `RESTRICT`
que bloqueara el borrado -- no fue necesaria ninguna migración nueva. Frontend: botón
"Eliminar" por fila + `ConfirmDialog` extendido con `confirmDisabled` (nuevo prop
opcional, reutilizable) -- checkbox de consentimiento + campo que exige escribir el
email exacto del usuario antes de habilitar el botón destructivo.

**§5.4 (submenú):** `RouteKey 'users'` → `'admin.usuarios'` (`/admin/usuarios`,
anidado bajo `/admin` en `AppRouter.tsx` y en `permissions.ts`) -- el Sidebar ya
renderiza sub-nav de forma 100% genérica por convención de `RouteKey` con punto
(`getSubNavItemsForRole`), sin cambios de lógica, solo mover el ícono de
`NAV_ICONS` a `SUB_NAV_ICONS`.

**§5.5 (dashboard de Admin, métricas reales):** nuevo `GET /analytics/admin/resumen`
(`SystemService.get_admin_resumen`, compone `UserRepository.count_por_estado()` +
`CatalogRepository.count_vendedores_activos()`/`count_almacenes()`, ambos nuevos) --
usuarios activos/inactivos reales de `public.usuarios`, vendedores/bodegas vigentes del
EDW (excluye el centinela `-1`, regla 12). Actividad reciente **no se duplicó**: ya la
cubre el log de auditoría paginado existente (`GET /analytics/admin/audit-logs`,
Fase 2 de una sesión anterior). Frontend: 4 `KpiCard` nuevas al inicio de
`DashboardAdmin.tsx`.

Validado extremo a extremo: `bi_backend` reconstruido -- **primer intento falló**
(`PydanticSchemaGenerationError: Unable to generate pydantic-core schema for
<class 'app.models.user.User'>`) por anotar `Page[User]` en el servicio; corregido
devolviendo `tuple[list[User], int]` desde el servicio y construyendo `Page[UserOut]`
en el router, igual que el patrón ya usado en `audit-logs`. Segundo build: arranque
limpio (6/6 modelos). `pytest backend/tests/unit` (187 passed -- 186 + 1 test nuevo de
`get_admin_resumen` -- 1 falla preexistente ajena); 2 tests de `test_system_service.py`
requirieron actualizar su fixture (`SystemService(...)` ganó 2 parámetros nuevos).
`pytest backend/tests/integration/test_admin_actualizacion.py` (20 passed, 4 skipped --
4 tests nuevos: paginación tipada, auto-eliminación rechazada, borrado real verificado
con 404 posterior, resumen con RBAC). `tsc --noEmit`/`oxlint` limpios en los 10 archivos
frontend tocados. Probado en vivo contra `bi_backend` real: `GET /users/?page=1&page_size=5`
y `GET /analytics/admin/resumen` responden con datos reales del EDW/`public.usuarios`
(11 activos, 36 inactivos -- acumulación conocida de usuarios de prueba de sesiones
anteriores, no un bug de esta fase; 24 vendedores activos, 14 bodegas).

## Fase 6.1 — Módulo Bodega: estado "Inmovilizado" (H-2, ALTO) — Aplicado

**El hallazgo más grave de datos del plan completo (H-2, severidad ALTO)**: un
artículo con stock > 0 y CERO salidas caía en `"Seguro"` porque `_dias_inventario`
devuelve `None` sin salidas y la rama `dias_inv > BODEGA_DIAS_EXCESO` es
matemáticamente inalcanzable con `None` — el reporte de "exceso de stock" filtraba
`estado == ESTADO_EXCESO`, así que el peor caso posible de sobre-stock (inmovilizado
total) era el único que **nunca aparecía**. Explica el caso reportado "Consignación
Verónica Sánchez: stock pero 0.0 uds/día".

**Corrección:**
- Estado nuevo `"Inmovilizado"` (distinto de `"Exceso"`, que sí rota, solo que muy
  lento) para `stock > 0` con cero salidas en una ventana de
  `BODEGA_DIAS_VENTANA_INMOVILIZADO` (nuevo, default 90 días) — deliberadamente más
  amplia que los 30 días que ya usa `salida_diaria` para el punto de reorden, para no
  marcar como estancado un artículo con un simple mes flojo (estacionalidad).
  `WarehouseRepository.get_inventario_productos`/`get_stock_por_almacen` ganan la
  columna `salidas_ventana_inmovilizado` (mismo patrón `FILTER` que ya usaban para el
  período anterior); `WarehouseService._enriquecer_producto` y
  `_inventario_matriz_completo` aplican la clasificación con prioridad sobre el resto
  de estados.
- `dias_inventario_baja_confianza` (nuevo, `ProductoStockReorden`): caso "El Rey" —
  `salida_diaria` por debajo de `BODEGA_MIN_SALIDA_CONFIABLE` (nuevo, default 0.5)
  marca "0 días de stock" como una urgencia de baja confianza, distinta de un
  artículo de alta rotación con el mismo número.
- El reporte "Productos en exceso de stock" (`get_reporte_analisis_mensual`) ahora
  incluye `Exceso ∪ Inmovilizado`, ordenado por capital inmovilizado
  (`stock × costo_unitario`) descendente — la pregunta de negocio real.
- **Bug real encontrado y corregido durante la validación en vivo, no solo en
  unit tests**: el truncado a 50 filas se aplicaba ANTES de separar por estado
  (`stock[:50]` con `orden_estado` que prioriza `Crítico` primero) — con 149 artículos
  críticos reales en el EDW, el corte de 50 nunca llegaba a `Exceso`/`Inmovilizado`,
  dejando el reporte vacío de nuevo pese a la clasificación ya corregida. Corregido
  truncando cada categoría por separado, después de filtrar.
- Frontend: `EstadoStock` (tipo TS) gana `'Inmovilizado'`; `BodegaAlmacenes.tsx`
  (badge, tinte de fila, filtro) y `BodegaReportes.tsx` (badge del contrato tipado
  genérico, resaltado igual que "Crítico") actualizados.

Validado extremo a extremo: 6 tests unitarios nuevos
(`test_warehouse_estado_stock.py`, cubren Inmovilizado/Exceso/baja-confianza y sus
casos negativos) + `pytest backend/tests/unit` (193 passed, 1 falla preexistente
ajena); `pytest` de integración de Bodega (28 passed, 1 skipped) y RLS (11 passed) sin
regresiones; `tsc --noEmit`/`oxlint` limpios. Probado en vivo contra `bi_backend`
real reconstruido: `GET /analytics/bodega/reportes/analisis-mensual` — **antes de esta
fase devolvía 0 filas en "Productos en exceso de stock"; después, 50 filas reales (41
Inmovilizado + 9 Exceso)**, confirmando el cierre completo del hallazgo H-2.

## Fase 6.2 — "Artículos sin movimiento en ventas por almacén" (H-9) — Aplicado

Reporte único parametrizado que reemplaza `QUERY_PRODUCTOS_SIN_VENTA` y
`QUERY_ARTICULOS_ESTANCADOS` (H-9: eran la misma query salvo un `HAVING`; ahora un
`?solo_con_stock=true|false` sobre el mismo endpoint):

- **Repositorio:** `WarehouseRepository.get_articulos_sin_venta` -- universo de
  `(producto, almacén)` con al menos un movimiento histórico; stock actual calculado
  agregando el kardex completo (`SUM(CASE es_entrada... es_salida...)`, regla 3),
  **no** desde `fact_inventario_snapshot` (solo poblada "hacia adelante", auditoría
  05); `NOT EXISTS` de ventas `FAC` en `[fecha_desde, fecha_hasta]`; última venta
  histórica (no solo del rango) vía `ROW_NUMBER() OVER (PARTITION BY almacen_sk,
  producto_sk ORDER BY fecha DESC, num_documento DESC)`. Reutiliza `_filtros_snapshot`
  (RLS por almacén ya incluida) y el helper `_rango_fechas` existentes.
- **Limitación heredada documentada, no introducida por este método (H-8):**
  `fact_movimientos_inventario` no tiene columna de estado de documento --
  confirmado en `etl/extractors/kardex_extractor.sql`, que no aplica ningún token
  `{ESTADO}` a diferencia de otros extractores -- así que una factura anulada puede
  aparecer como "última venta" si es la más reciente. Corregirlo requiere un cambio de
  ETL/esquema (agregar la columna, re-extraer desde SAP) fuera del alcance de este
  reporte puntual; documentado en vez de fingir que no existe.
- **Servicio:** `WarehouseService.get_reporte_sin_venta` devuelve el contrato
  `ReporteBodegaResponse` ya existente (hereda gratis Excel/tabla/futuro PDF, sin
  código de presentación nuevo); `valor_inmovilizado` = `stock × costo`,
  `dias_desde_ultima_venta` derivado en Python (nunca en SQL, coherente con
  `_enriquecer_producto`).
- **Endpoint:** `GET /reportes/sin-venta` (mismo router que los otros 3 reportes) +
  `?busqueda=` (código o nombre, `ILIKE`) y `?solo_con_stock=` (default `true`).
  Sin columna `Cliente` (decisión del usuario, §6.0 del plan).
- **Frontend:** tarjeta nueva en `BodegaReportes.tsx`; toggle "solo con stock" +
  buscador visibles solo para este tipo de reporte (`extra` opcional nuevo en
  `useReporteBodega`/`getReporteBodega`, sin ensuciar los filtros globales
  compartidos por los otros 3 reportes).

## Fase 6.4 — Nombres de archivo Excel con fecha/hora (H-4) — Aplicado

`GET /reportes/{tipo}/excel` genera el nombre en el backend (zona horaria del
servidor): `reporte_{tipo}_{YYYY-MM-DD_HH-MM}.xlsx`. El frontend (`descargarReporteExcel`
en `services/bodega.ts`) leía el `Content-Disposition` del backend legado, que nunca
llevaba fecha, y fijaba su propio nombre estático sin fecha (`link.download =
"reporte_${tipo}.xlsx"`) -- **ese `download` estático habría anulado el fix del
backend en el navegador** (cuando se asigna `<a download="X">` sobre un blob creado
con `URL.createObjectURL`, el navegador usa el atributo `download`, no la cabecera
HTTP original). Corregido leyendo el nombre real del header `content-disposition` de
la respuesta y usándolo en `link.download`, con el nombre estático solo como
`fallback` si el header faltara.

Validado extremo a extremo (ambas fases): 4 tests de integración nuevos (contrato
tipado del reporte `sin-venta`, `solo_con_stock` como subconjunto real, búsqueda por
código/nombre, sin columna `cliente`, nombre de archivo con fecha/hora vía regex) +
`pytest backend/tests/unit` (193 passed, 1 falla preexistente ajena);
`pytest backend/tests/integration/test_warehouse_actualizacion_bodega.py` (24 passed,
0 failed) y el resto de la suite de Bodega/RLS sin regresiones (39 passed, 1 skipped
en total); `tsc --noEmit`/`oxlint` limpios. Probado en vivo contra `bi_backend` real:
`GET /reportes/sin-venta` (500 estancados reales, $59.544,87 en valor inmovilizado, 90
nunca vendidos), `?solo_con_stock=false&busqueda=HANKOOK` (73 filas reales), y el
header `Content-Disposition: attachment; filename="reporte_sin-venta_2026-07-29_17-00.xlsx"`
confirmado con fecha/hora real del servidor.

Pendiente de Fase 6: §6.3 (pulido UI/UX, ya cubierto en gran parte por el contrato
tipado existente), §6.5 (PDF real generado en backend, requiere dependencia nueva),
§6.6 (motivos de transferencia más accionables), §6.7 (QUERY_KARDEX_MOVIMIENTOS).

## Fase 6.3 — UI/UX de los tres (ahora cuatro) reportes de abastecimiento — Verificado sin hallazgos

El plan pedía que cada reporte de `BodegaReportes.tsx` mostrara título + pregunta de
negocio que responde + descripción explícita, **dentro del contrato tipado** ya
establecido en la Fase 5 del plan de Bodega (auditoría 32) — no una reescritura nueva.
Verificado en el código actual (`REPORTES` en `BodegaReportes.tsx:14-39`): las 4
tarjetas de selección (incluida `sin-venta`, agregada en la Fase 6.2 de esta misma
sesión) ya declaran `titulo`/`pregunta`/`descripcion` y se renderizan en ese orden
exacto (pregunta en negrita como gancho principal, título y descripción como
contexto). Sin cambios de código — la Fase 5 anterior y la Fase 6.2 de esta sesión ya
satisfacen el objetivo.

## Fase 6.6 — Motivos de transferencia más accionables (§6.4) — Aplicado

**Hallazgo:** `/transferencias-sugeridas` ya calculaba `justificacion`/`confianza`/
`beneficio_neto_estimado` (RN-B9, Fase 4 de `plan_actualizacion_modulo_bodega.md`),
pero el texto libre `motivo` que ve el usuario de Bodega solo enumeraba "días de stock"
y "uds/día" en origen y destino, sin traducir esos números en una acción concreta ni en
el valor monetario inmovilizado — obligaba al lector a hacer el cálculo de "¿cuánto me
conviene mover y por cuánto tiempo me alcanza?" a mano.

**Corrección:** nuevo `WarehouseService._motivo_transferencia` (extraído del cuerpo de
`_transferencias_completo`, mismos datos ya calculados en `_justificacion_transferencia`,
sin consulta nueva al EDW) construye el texto en 3 partes, siguiendo literalmente el
formato de ejemplo del plan:
1. **Origen:** si tiene salidas registradas, "`{días}` días de stock en `{almacén}`
   (`{uds}`, `${valor}`)"; si no tiene ninguna salida en la ventana de justificación
   (`_VENTANA_JUSTIFICACION_DIAS`), "Sin salidas en los últimos `{N}` días en
   `{almacén}` (`{uds}`, `${valor}` inmovilizados)" — el valor monetario sale de
   `stock_actual × costo_unitario`, ya presente en la fila del origen.
2. **Destino:** demanda mensual observada (`demanda_media_destino × 30`) y meses de
   historial (`meses_con_venta_destino`), más los días de cobertura actuales; si no hay
   demanda medible, degrada a solo mostrar los días de cobertura (nunca inventa un
   promedio de una serie vacía).
3. **Acción:** "Transferir `{cantidad}` uds cubre `{meses}` meses de su demanda" —
   `cantidad_transferir / demanda_mensual_destino` — o solo "Transferir `{cantidad}`
   uds" si la demanda mensual no es calculable.

**Decisión ya tomada, no revisitada aquí:** el ejemplo "Cliente asociado: X" del
requerimiento original se omite (§6.0 del plan): aunque
`fact_movimientos_inventario.cliente_sk` está poblada para `FAC`, los reportes de
Bodega no llevan identidad de cliente por decisión del usuario.

Validado: `pytest backend/tests/unit` (193 passed, 1 falla preexistente ajena, sin
relación); `pytest backend/tests/integration/test_warehouse_actualizacion_bodega.py`
(22 passed) y `test_bodega_rls.py` (todas las pruebas pasan en ejecución aislada; los 3
errores vistos en una corrida combinada fueron el limitador de tasa de login de 5/min,
agotado por las pruebas manuales en vivo de esta misma fase, no una regresión).
Probado en vivo contra `bi_backend` reconstruido: `GET /transferencias-sugeridas`
devuelve, por ejemplo, `"Sin salidas en los últimos 180 días en PELILEO (4 uds, $624
inmovilizados). ATAHUALPA vendió 33 uds/mes en los últimos 7 meses y tiene 10 días de
cobertura. Transferir 4 uds cubre 0.1 meses de su demanda."` — el formato exacto que
pedía el plan, con datos 100% reales del EDW.

Pendiente de Fase 6: §6.5 (PDF real generado en backend, requiere decisión de
dependencia), §6.7 (`QUERY_KARDEX_MOVIMIENTOS`).

## Fase 6.7 — `QUERY_KARDEX_MOVIMIENTOS` migrada al EDW (H-11) — Aplicado

`QUERY_BODEGAS` ya estaba implementada (`CatalogRepository.get_almacenes`, expuesta en
`GET /users/almacenes`) — no se reimplementó, confirmado sin cambios.

**Hallazgo (H-11, MEDIO):** la query de Producción tenía un `GROUP BY` sin ninguna
función de agregación (un `DISTINCT` disfrazado) y mezclaba dos granos: filas a nivel
`(bodega, artículo)` con `a.exiact` (`ExistenciaGlobal`), la existencia **global** del
artículo sin desglosar por bodega. `edw.dim_producto` no almacena esa columna — no hay
equivalente directo en el EDW.

**Corrección:** nuevo `tipo=kardex` del contrato tipado ya existente
(`ReporteBodegaResponse`, mismo patrón que `sin-venta` de la Fase 6.2 — hereda gratis
render, Excel y (cuando exista) PDF). `WarehouseRepository.get_movimientos_kardex`
hace un `SELECT` directo sobre `edw.fact_movimientos_inventario` al grano de un
movimiento individual (corrige el `GROUP BY` sin agregación con una consulta que
simplemente no agrupa lo que no debe agregarse). `existencia_global` se deriva sumando
el kardex completo (todos los almacenes, todo el histórico) por producto — la misma
fórmula de dirección por `es_entrada`/`es_salida` que usa el resto del módulo (regla 3,
corrige H-7 automáticamente) — y la columna se etiqueta explícitamente "Existencia
global (kardex, todos los almacenes)" en el contrato, para no presentarla en silencio
como si fuera el mismo dato que `exiact` de Producción.

**Bug evitado, no heredado de la query original:** el resto del módulo Bodega usa
`_filtros_snapshot` para traducir `tipo_movimiento` a "artículos que ALGUNA VEZ
tuvieron ese tipo de movimiento" — semántica correcta para reportes agregados por
artículo, pero **incorrecta** para un listado de movimientos individuales (filtrar por
`FAC` habría devuelto también filas `TRA`/`CPA` de productos que alguna vez se
vendieron). `get_movimientos_kardex` filtra directo por `m.tipo_movimiento` en la fila,
no reutiliza esa semántica — cubierto por un test dedicado
(`test_kardex_filtro_tipo_movimiento_filtra_por_fila_no_por_articulo`).

**Columna `Cliente`:** se omite igual que en el resto de reportes de Bodega (§6.0,
decisión del usuario) — `FechaUltimaVenta`/`NumeroFactura` no aplican aquí (esto es un
listado de movimientos, no de última venta), pero si en el futuro se necesitara,
seguiría la misma decisión.

Validado: `pytest backend/tests/unit` (193 passed, 1 falla preexistente ajena);
`pytest backend/tests/integration/test_warehouse_actualizacion_bodega.py` (22 passed,
incluye 2 tests nuevos de kardex + el 5º caso del contrato tipado parametrizado);
`tsc --noEmit`/`oxlint` limpios en los 2 archivos frontend tocados. Probado en vivo
contra `bi_backend` reconstruido: `GET /reportes/kardex?fecha_desde=2026-01-01&
fecha_hasta=2026-01-15` devuelve 1.000 movimientos reales (tope del límite, 2.058
unidades de entrada, 1.548 de salida); con `tipo_movimiento=TRA` las 1.000 filas
devueltas son 100% `TRA` (confirmando que el filtro es por fila, no por artículo) con
`existencia_global` poblada (ej. `7.0` para un artículo real de "ATAHUALPA").

Con esto se cierra por completo la Fase 6 del plan salvo §6.5 (PDF real, pendiente de
decisión de dependencia nueva).

## Fase 6.5 — PDF real generado en backend (H-3) — Aplicado

**Decisión del usuario:** WeasyPrint (entre las 3 opciones presentadas: WeasyPrint,
ReportLab, xhtml2pdf) — renderiza HTML/CSS a PDF con alta fidelidad, permitiendo
reutilizar el mismo layout de negocio que ya tiene el reporte en pantalla sin
reescribirlo celda por celda como exigiría ReportLab.

**Hallazgo (H-3):** el botón "Imprimir / PDF" de `BodegaReportes.tsx` llamaba
`window.print()`, heredando el layout de pantalla (paginación rota, tablas cortadas,
gráficos recortados, nav/sidebar impresos) — no era un PDF real, dependía enteramente
del motor de impresión del navegador del usuario.

**Corrección:** nuevo `GET /reportes/{tipo}/pdf` (mismo despachador `_generar_reporte`
que ya usan `/reportes/{tipo}` y `/reportes/{tipo}/excel` — una sola fuente de datos
para pantalla, Excel y PDF). `WarehouseService`/`WarehouseRepository` no cambian: el
nuevo `app/services/warehouse_pdf_export.py::reporte_a_pdf` consume el mismo contrato
tipado `ReporteBodegaResponse` que ya alimenta `warehouse_export.py` (Excel) y
construye su propio documento HTML/CSS (banda de KPIs, interpretación, una tabla por
sección con el mismo resaltado de prioridad "Alta"/"Crítico"/"Inmovilizado" que el
Excel), convertido a PDF con `WeasyPrint`. Mismo `Content-Disposition` con fecha/hora
del servidor que la Fase 6.4 (`reporte_{tipo}_{YYYY-MM-DD_HH-MM}.pdf`). El frontend
(`descargarReportePdf` en `services/bodega.ts`, mismo patrón que
`descargarReporteExcel`) reemplaza `window.print()` por una descarga real; el botón
pasa de "Imprimir / PDF" a "Descargar PDF" con estado de carga propio.

**Dependencias nuevas (`backend/requirements.txt`):** `weasyprint>=62.0,<63.0` +
`libpango-1.0-0`/`libpangocairo-1.0-0`/`libgdk-pixbuf-2.0-0`/`libcairo2`/
`fonts-dejavu-core`/`shared-mime-info` en `backend/Dockerfile` (WeasyPrint las carga
vía `ctypes` en tiempo de import, no son dependencias de `pip`). El nombre del paquete
`libgdk-pixbuf2.0-0` (con punto) no existe en Debian 12 "bookworm" -- es
`libgdk-pixbuf-2.0-0` (con guion); corregido antes del primer build exitoso.

**Bug real encontrado y corregido durante la validación en vivo (no solo en unit
tests):** con `weasyprint==62.3` sin pin de su dependencia `pydyf`, `pip` resolvía
`pydyf==0.12.1`, y **todo** intento de generar un PDF fallaba en producción con
`AttributeError: 'super' object has no attribute 'transform'`
(`weasyprint/pdf/stream.py` llama `pydyf.Stream.transform(...)`, un método que
`pydyf` 0.12.x eliminó/renombró a `set_matrix`) — el endpoint devolvía 500 en el
100% de los requests pese a que el build de Docker y el arranque del backend eran
limpios. Corregido fijando `pydyf==0.11.0` explícitamente en `requirements.txt`
(última versión verificada compatible con `weasyprint==62.3`).

**Import diferido, no a nivel de módulo:** `reporte_a_pdf` importa `weasyprint.HTML`
dentro de la función, no en el encabezado del archivo — WeasyPrint carga
Pango/Cairo/GObject vía `ctypes` en el momento del `import`, así que un import a nivel
de módulo habría roto el arranque de **todo** el backend (no solo el endpoint de PDF)
en cualquier entorno sin esas librerías de sistema instaladas, incluyendo `pytest`
corriendo en Windows fuera de Docker (confirmado en vivo: `import weasyprint` falla
con `OSError: cannot load library 'gobject-2.0-0'` en este entorno de desarrollo
Windows, que no tiene el runtime GTK).

**Recorte a 200 filas por sección en el PDF** (`_MAX_FILAS_PDF`, no aplica al Excel,
que sigue incluyendo todas): un PDF con miles de filas de `kardex` es ilegible e
inmanejable de paginar; se declara explícitamente en el pie de cada tabla cuando el
recorte aplica ("Mostrando 200 de N filas — el Excel incluye todas"), mismo patrón que
ya usaba `BodegaReportes.tsx` en pantalla (`MAX_FILAS = 60`).

Validado extremo a extremo: `bi_backend` reconstruido desde cero con el pin de `pydyf`
ya en `requirements.txt` (confirma que el fix es reproducible, no un parche manual en
el contenedor en ejecución); `pytest backend/tests/unit` (193 passed, 1 falla
preexistente ajena) corrido tanto en el host como dentro del contenedor;
`pytest backend/tests/integration/test_warehouse_actualizacion_bodega.py` corrido
**dentro del contenedor real** (única forma de probar WeasyPrint, que requiere las
librerías de sistema que solo existen ahí) — **28 passed** (incluye
`test_reporte_pdf_devuelve_documento_real_con_fecha_hora_en_el_nombre`, que verifica
`content-type: application/pdf`, el nombre de archivo con fecha/hora, y que el
contenido empieza con la firma real `%PDF-`; y `test_reporte_pdf_funciona_para_los_5_
tipos`, parametrizado sobre los 5 tipos de reporte); `tsc --noEmit`/`oxlint` limpios.
Probado en vivo con `curl` contra los 5 tipos de reporte: los 5 devuelven `HTTP 200`
con firma `%PDF-` real y tamaños de archivo realistas (justificación 390KB,
transferencias 221KB, análisis mensual 134KB, sin-venta 61KB, kardex 56KB).

Con esto se cierra por completo la Fase 6 del plan.

## Fase 2 §2.4 — Auditoría A-0.4: alineación TypeScript ↔ Pydantic — Aplicado

Auditoría estática, campo a campo, de cada modelo TypeScript de `frontend/src/types/`
contra el schema Pydantic real que lo alimenta (12 pares de archivos revisados,
cubriendo `admin.ts`, `auth.ts`, `bodega.ts`, `cartera360.ts`, `commissionConfig.ts`,
`crossSelling.ts`, `gerencia.ts`, `goals.ts`, `notifications.ts`, `pagination.ts`,
`system.ts`, `ventas.ts`). 8 de 12 pares sin hallazgos. 4 desalineaciones encontradas,
todas corregidas:

### Hallazgo real, ALTO — `VentasKPIs` rompía 3 de 4 KPI del dashboard principal de Ventas

`frontend/src/types/ventas.ts` declaraba dos tipos para el **mismo** endpoint
`GET /analytics/ventas/goals`: `VentasKPIs` (campos `ventas_actuales`,
`cumplimiento_pct`, `clientes_activos`, `churn_promedio` — **ninguno existe en el
backend real**, que devuelve `VPKPIVentas`: `meta_mensual`, `cumplimiento_actual`,
`meta_proyectada`, `ranking_vendedores`) y `VentasGoalsTracking` (el tipo correcto, ya
usado por `VendorGoalDashboard.tsx`). `DashboardVentas.tsx` — la vista principal de
Ventas — usaba el tipo roto vía `useSalesGoals`/`getSalesGoals`: las tarjetas "Ventas
Actuales", "Cumplimiento" y "Clientes Activos" leían campos que la respuesta real
nunca trae (`undefined`), degradando a `NaN`/guiones en el 100% de las cargas.
Aparentemente un desarrollo previo detectó el desajuste y creó `VentasGoalsTracking`
como corrección para el panel de metas del vendedor, pero nunca actualizó el
dashboard original que causó el hallazgo.

**Corrección:** `getSalesGoals` (services/ventas.ts) ahora devuelve
`VentasGoalsTracking` (tipo correcto, no uno nuevo); `VentasKPIs` se eliminó por
completo (tipo muerto, sin otro consumidor); `DashboardVentas.tsx` reescribe las 4
KPI cards con los campos reales: Meta Mensual, Ventas Actuales (`cumplimiento_actual`
pese al nombre confuso del campo — es venta real acumulada en $, no un porcentaje),
Cumplimiento % (derivado en frontend: `cumplimiento_actual / meta_mensual`, el backend
no envía el porcentaje ya calculado) y Meta Proyectada (`meta_proyectada`, reemplaza
la tarjeta "Clientes Activos" que nunca tuvo datos reales detrás). Confirmado en vivo
contra `bi_backend`: la respuesta real trae exactamente `meta_mensual`,
`cumplimiento_actual`, `meta_proyectada`, `ranking_vendedores` — coincide 1:1 con el
tipo corregido.

### Hallazgos MEDIO/BAJO, sin bug activo (campos faltantes o muertos, sin consumidor roto)

- `bodega.ts` `ProductoStockReorden` no declaraba `dias_inventario_baja_confianza`
  (RN-B11, caso "El Rey", Fase 6.1). Sin impacto visible hoy porque `useStockReorden`
  no tiene ningún consumidor en el frontend (la tabla que lo usaba se retiró de
  `DashboardBodega.tsx` en una fase anterior; el endpoint se conserva porque
  `NotificationService` lo sigue invocando desde el backend) — corregido para que el
  tipo sea correcto si se vuelve a consumir.
- `ventas.ts` `MetaSugerida` no declaraba 4 campos que el backend sí envía
  (`componente_estacional`, `componente_tendencia`, `factor_tendencia_aplicado`,
  `coeficiente_variacion`) — el tipo hermano `goals.ts::MetaSugeridaDesglose` (vista de
  gerencia del mismo dato) sí los tenía completos. `VendorGoalDashboard.tsx` no los lee
  hoy, así que no había bug activo — corregido por completitud del contrato.
- `gerencia.ts` `GerenciaKPIs.ventas_consolidadas?` era un campo sin contraparte en el
  backend y sin ningún consumidor — eliminado (código muerto, no un campo faltante).

Validado: `npx tsc --noEmit` y `npx oxlint` limpios en los 6 archivos tocados
(`types/ventas.ts`, `types/bodega.ts`, `types/gerencia.ts`, `services/ventas.ts`,
`hooks/ventas.ts`, `pages/DashboardVentas.tsx`); `pytest backend/tests/unit` sin
regresiones (193 passed, 1 falla preexistente ajena — esta fase no tocó backend);
confirmado en vivo con `curl` contra `GET /analytics/ventas/goals` que el contrato
real coincide exactamente con el tipo corregido.

## Fase 2 §2.3 — Filtros híbridos texto + combobox — Aplicado

El proyecto ya tenía un componente `Autocomplete<T>` (`components/ui/Autocomplete.tsx`,
Fase de Venta Cruzada) para el caso "búsqueda parcial contra el backend por cada tecla,
solo selecciona de resultados reales" (clientes/productos, catálogos grandes/paginados).
Faltaba el caso complementario que pide el punto 3 del plan: un combobox tipeable sobre
un catálogo **ya cargado en memoria** (`almacenes`/`categorias`/`proveedores` de
`GET /analytics/bodega/filtros`, listas completas y acotadas) -- hoy resueltos con
`<select>` nativo, incómodo de recorrer si el catálogo crece (multi-sucursal).

**Nuevo `components/ui/ComboboxField.tsx`:** filtrado 100% client-side (sin llamada al
backend por tecleo, a diferencia de `Autocomplete`) sobre un `string[]` ya disponible;
solo permite seleccionar un valor que exista en `options` -- **nunca texto libre**,
consistente con el punto 3 del plan ("donde el backend exige un código exacto, se
deshabilita el texto libre"): estos filtros siempre exigen el valor exacto del catálogo
(`al.nombre_almacen = :almacen`, `p.clase = :categoria`, etc. en
`WarehouseRepository._filtros_snapshot`), nunca aceptan una búsqueda parcial, así que
no había ambigüedad en el diseño. Mismo patrón visual/posicionamiento de dropdown que
`Autocomplete` (portal a `document.body`, cálculo de espacio arriba/abajo del viewport)
para consistencia de UX, pero disparado por un botón tipo `<select>` en vez de un input
de búsqueda siempre visible.

**Aplicado en `BodegaFilterBar.tsx`:** los selectores de Almacén, Categoría y Proveedor
(los 3 catálogos que pueden crecer con más sucursales/proveedores reales) pasan de
`<Select>` nativo a `<ComboboxField>`; "Tipo de movimiento" se deja como `<Select>`
nativo (catálogo cerrado de 8 valores fijos, sin beneficio real de un buscador). La
dependencia declarativa `categoria → proveedor` de la Fase 2 §2.2 (limpieza del
proveedor al cambiar de categoría, deshabilitado con leyenda si no hay proveedores para
esa categoría) se conserva sin cambios -- `ComboboxField` solo reemplaza el control de
UI, no la lógica de filtrado inteligente ya validada.

Con esto se cierra por completo la Fase 2 del plan.

Validado: `npx tsc --noEmit` y `npx oxlint` limpios; `npm run build` (build de
producción completo) sin errores nuevos. **Limitación conocida y ya documentada del
entorno** (sin `chromium-cli` en este Windows): no fue posible una verificación visual
en navegador real del dropdown/posicionamiento -- queda como paso manual del usuario,
igual que el resto de componentes visuales de esta sesión.

## A-0.3 — ¿`sucursal` discrimina para el rol `ventas`? (decisión B-3) — Ejecutada, ALTO

**Método:** `SELECT` real contra el EDW (`bi_postgres_edw`), sin escrituras.

```sql
-- Últimos 12 meses, documentos válidos (estado ≠ 'A', regla 1)
WITH ventas_validas AS (
  SELECT f.vendedor_sk, f.sucursal_sk
  FROM edw.fact_ventas_detalle f
  JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
  JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
  WHERE f.vendedor_sk <> -1 AND ed.estado_documento_sk <> -1
    AND d.fecha_completa >= CURRENT_DATE - INTERVAL '12 months'
)
SELECT vendedor_sk, COUNT(DISTINCT sucursal_sk) AS n_sucursales
FROM ventas_validas GROUP BY vendedor_sk;
```

**Resultado:** de 7 sucursales totales en el EDW (`edw.dim_sucursal`, excluyendo el
centinela), **10 de 11 vendedores activos en los últimos 12 meses transaccionan en 4 a
7 de esas 7** (90.9%, promedio 5.18 sucursales/vendedor, máximo 7/7). Solo 1 vendedor
está confinado a una sola sucursal. El mismo patrón se confirma con el histórico
completo (85.0%, 17 de 20 vendedores, promedio 4.40). Detalle por vendedor (12 meses):
`ALMACEN ATAHUALPA` 7/7, `ALMACEN EL REY`/`IZAMBA`/`LOS CHASQUIS`/`PELILEO`/`SALCEDO`/
`WILLIAN SANCHEZ` 6/7, `LUIS ALBERTO LOPEZ LOPEZ` 5/7, `LUIS SANCHEZ`/`WILLIANS JESUS
SUPE` 4/7, `SACOTTO GUEVARA EDWIN ALB` 1/7.

**Impacto real, no solo teórico:** `resolve_sucursal_filter(allow_override=False)`
forzaba a cada usuario `ventas` a `usuarios.sucursal` (un valor único y fijo por
cuenta) en `GET /analytics/ventas/goals` y `/goals/forecast-cierre` -- para un
vendedor típico (5-7 sucursales reales), esto le ocultaba al propio vendedor la
mayoría de sus ventas reales en su propio dashboard. No es "el filtro no discrimina
bien": estaba activamente mostrando datos incompletos.

**Decisión B-3 (usuario, 2026-07-29): retirar `sucursal`, usar `vendedor`** -- ya es
el discriminador correcto y ya se usa en el resto de este mismo router
(`_codven_restriccion`, `mi-comision`, `meta-sugerida`, `churn-risk`, Venta Cruzada) y
en Metas/Comisiones (regla de negocio 10: el grano de `metas_comerciales_operativas`
es `(anio, mes, id_vendedor_origen)`, nunca sucursal).

**Aplicado:**
- `AnalyticsRepository.get_sales_performance` gana `vendedor: str | None` (además de
  `sucursal`, que se conserva para el uso exploratorio voluntario de gerencia en
  `/gerencia/goals/ai-summary`, sin cambios): filtra `query_meta`/`query_actual` por
  `id_vendedor_origen`/`dim_vendedor.codven` en vez de sucursal; `query_ranking` se
  omite cuando hay `vendedor` (comparar un vendedor contra sí mismo no aporta nada, y
  ningún consumidor del panel personal la usa -- solo `ai-summary`, de gerencia, la
  sigue pidiendo sin `vendedor`).
- `sales.py`: `/goals` y `/goals/forecast-cierre` cambian de
  `resolve_sucursal_filter(allow_override=False)` a `_codven_restriccion` (ya existía
  en el mismo archivo para el resto de endpoints -- se reordenó antes de su primer uso).
- `GoalMLService.forecast_cierre` gana `vendedor_nombre` (además de `sucursal`):
  `DatasetRepository.get_daily_sales_history` ya soportaba un filtro `vendedor` (por
  `nombre_vendedor`, no `codven` -- mismo campo que usa el selector de vendedor de
  Gerencia, Fase 3), así que la ruta resuelve `codven -> nombre_vendedor` vía
  `CatalogRepository.get_vendedor_activo` antes de llamar al servicio de ML, para que
  la meta (personal) y la proyección (ahora también personal) sean comparables --
  mezclar una meta personal con una proyección consolidada de toda la empresa habría
  sido peor que el bug original.

Validado extremo a extremo: `pytest backend/tests/unit` (194 passed -- 1 test nuevo,
1 falla preexistente ajena y fechada); `pytest backend/tests/integration -k "sales or
ventas or goal"` (24 passed, 1 skipped, sin regresiones); `bi_backend` reconstruido con
arranque limpio. Probado en vivo con datos reales del EDW: el usuario de prueba
`ventas_gye@empresa.com` (rol `ventas`) tiene `id_vendedor_origen='102'`, un código que
**no existe** en `edw.dim_vendedor` (desalineación de datos semilla preexistente, ya
documentada en el historial de este proyecto -- no introducida ni corregida aquí,
fuera de alcance), así que su respuesta es correctamente `0`/`Consolidado` (RLS
funcionando: sin datos para ese código, no debe inventar ninguno). Para confirmar la
lógica con un vendedor real, se ejercitaron los servicios directamente dentro del
contenedor con el código real `VEN02` (`WILLIAN SANCHEZ`, usuario real
`vwilliam@gmail.com`, sin credenciales de prueba conocidas): `get_sales_kpis(vendedor=
'VEN02', anio=2026, mes=7)` devolvió `meta_mensual=$58.098,83` / `cumplimiento_actual=
$54.976,83` -- coincide exactamente con una consulta SQL manual de control y con la
fila de `WILLIAN SANCHEZ` ya vista en el ranking de `ai-summary`; `forecast_cierre`
con `vendedor_nombre='WILLIAN SANCHEZ'` devolvió `ventas_mes_actual=$54.976,83`
(idéntico a `cumplimiento_actual`, confirma consistencia meta↔proyección) y
`sucursal: 'WILLIAN SANCHEZ'` en el label (antes habría sido "Sucursal Guayaquil" o
similar, mezclando ~6 vendedores/tiendas distintas).

**Nota adicional (no corregida, fuera de alcance de esta fase):** durante la
verificación se encontró `backend/tests/tests/` -- una copia duplicada y **no
versionada** (`git status` la marca `??`, no está en el índice) de `backend/tests/`,
desactualizada (contiene las aserciones viejas de `test_analytics_service.py`, previas
a este fix). Corre `pytest tests/` sin acotar produce falsos positivos por esta
duplicación. Se documenta para que el usuario decida si eliminarla; no se tocó en esta
sesión al ser un hallazgo fuera del alcance de A-0.3/B-3 y un directorio no versionado
cuyo origen no está confirmado.

Con esto se cierra B-3 y la Fase 7 queda desbloqueada.

## Hallazgo Bodega-sucursal — retiro de `sucursal` como filtro de seguridad en Bodega — Ejecutada, ALTO

**Contexto:** a raíz de la instrucción explícita del usuario tras B-3 ("no se debe
utilizar la sucursal sino revisa el almacen y los vendedores, pero no en sucursal
por que esa no es la regla de negocio"), se auditó el resto del sistema en busca de
otros usos de `sucursal` como filtro de seguridad (no solo Ventas). Se encontró que
el módulo Bodega (`backend/app/api/routes/warehouse.py`) forzaba en **todos** sus
endpoints reales (`/kpis`, `/salidas-forecast`, `/rotacion-matriz`, `/top-productos`,
`/salidas-categoria`, `/stock-reorden`, `/necesidad-compra`, `/inventario-matriz`,
`/transferencias-sugeridas`, `/reportes/{tipo}[/excel|/pdf]`) una restricción
adicional `sucursal_bodega = resolve_sucursal_filter(allow_override=False)`, aplicada
en AND junto a la RLS real por almacén (`resolve_almacenes_filter` / RN-B10, ya
correcta desde la Fase 1 de este plan, H-1) sobre `usuarios.sucursal`.

**Evidencia (SELECT contra el EDW real, sin escrituras):**

```sql
SELECT a.codalm, a.nombre_almacen, a.establ, s.codigo_sucursal, s.nombre_sucursal
FROM edw.dim_almacen a
LEFT JOIN edw.dim_sucursal s ON s.establ = a.establ AND s.codemp = a.codemp
ORDER BY a.codalm;
```

`establ='003'` ("PRINCIPAL: MATRIZ") agrupa **8 de los 15 almacenes reales**, incluidas
camionetas de vendedores individuales (`WILLIAN SANCHEZ TBM3626`, `LUIS SANCHEZ TBL6731`,
`TRAJANO PENAFIEL TBF-8236` -- placas de vehículo) y bodegas de consignación
(`CONSIGNACION BETTY GALLEGOS`, `CONSIGNACION VERONICA SANCHEZ`) junto con la tienda
física real (`WILLIAN SANCHEZ TBM3626` es en realidad el almacén 03, distinto del físico
"ATAHUALPA"): `sucursal` es una agrupación demasiado gruesa para ser la unidad de acceso
real de Bodega, que siempre fue `codalm` (`usuario_almacenes`, ya implementado).

**Bug real confirmado en vivo (blackout total, no parcial):**

```sql
SELECT u.id, u.email, u.sucursal, u.todos_los_almacenes,
       array_agg(ua.codalm ORDER BY ua.codalm) AS almacenes_asignados
FROM public.usuarios u
LEFT JOIN public.usuario_almacenes ua ON ua.usuario_id = u.id
JOIN public.roles r ON r.id = u.rol_id
WHERE r.nombre = 'bodega' AND u.es_activo = true
GROUP BY u.id, u.email, u.sucursal, u.todos_los_almacenes;
```

El usuario real `bodega_quito@empresa.com` (`todos_los_almacenes=true`, debía ver
**todo** el inventario) tiene `usuarios.sucursal = 'Matriz Quito'` -- valor que **no
existe** en `edw.dim_sucursal.nombre_sucursal` (los 7 valores reales son variantes como
`SUC. EL REY`, `PRINCIPAL: MATRIZ`, `SUC.: SALCEDO`, etc., ninguno "Matriz Quito").
Como el filtro se aplica con `su.nombre_sucursal = :sucursal`, este usuario recibía
**0 filas en el 100% de sus KPIs/reportes**, silenciosamente -- sin mensaje de error,
sin selector de sucursal visible en el frontend (`BodegaFilterBar.tsx` nunca expuso
ese filtro, confirmado por grep) que le permitiera siquiera notar la causa. Validado
ejecutando la consulta real del endpoint legado `/kpis-inventory` dentro del contenedor
con `sucursal='Matriz Quito'`: `(items_sobrestock=0, items_riesgo_desabasto=0)`.

**Corrección aplicada:**

- `backend/app/api/routes/warehouse.py`: se retira `sucursal_bodega`/
  `resolve_sucursal_filter` de los 15 endpoints reales del módulo; dejan de recibir/
  propagar `sucursal` (siempre `None` en adelante -- la RLS real sigue siendo
  `almacenes_permitidos`, ya inyectada en el constructor de `WarehouseRepository`
  desde la Fase 1). El parámetro `sucursal` se conserva en `WarehouseService`/
  `WarehouseRepository`/`_generar_reporte` (siempre `None`) para no forzar un refactor
  de ~15 métodos que ya no reciben ese valor -- riesgo/beneficio no lo justificaba
  frente al objetivo real (que `sucursal` deje de restringir datos).
- Endpoint legado `/kpis-inventory` (sin consumidor en el frontend actual, confirmado
  por grep, pero sigue siendo un endpoint autenticado alcanzable): en vez de dejarlo
  con la misma restricción rota, se migró a la misma RLS real del resto del módulo.
  `AnalyticsRepository.get_inventory_alerts(sucursal=...)` →
  `get_inventory_alerts(almacenes_permitidos: list[str] | None = ...)`, filtrando
  `edw.fact_inventario_snapshot` por `al.codalm IN (...)` (join a `dim_almacen`, la
  tabla ya tiene `almacen_sk` propio, confirmado con `\d edw.fact_inventario_snapshot`)
  en vez de `dim_sucursal`; lista vacía = `1=0` (sin acceso), `None` = sin restricción
  (privilegiado). `AnalyticsService.get_warehouse_kpis` actualizado a juego.
- Documentación del router (`warehouse.py`, docstring de módulo) corregida: ya no dice
  "el rol bodega queda forzado a su sucursal", dice "forzado a sus almacenes asignados".

**Validado extremo a extremo:**

- `python -m py_compile` de los 3 archivos tocados -- limpio.
- `pytest backend/tests/unit` -- 194 passed, 1 falla preexistente ajena (misma de
  siempre, dependiente de fecha del sistema).
- `bi_backend` reconstruido (`docker compose build backend` + `up -d`), arranque limpio,
  6/6 modelos ML cargados.
- `pytest backend/tests/integration/test_warehouse_actualizacion_bodega.py` en el host:
  28 passed (los 6 tests de PDF fallan en el host por la limitación ya documentada de
  WeasyPrint en Windows sin GTK, no por este cambio); repetido **dentro del contenedor
  real** (única forma de probar WeasyPrint): 33 passed (incluye los 6 de PDF).
- `pytest backend/tests/integration/test_bodega_rls.py`: pasa completo en una corrida
  aislada salvo el limitador de `/auth/login` (5/min) agotado por corridas manuales
  repetidas de esta misma sesión de validación -- mismo artefacto ya documentado en
  la Fase 6.6, no una regresión.
- **Probado en vivo dentro del contenedor**, comparando el filtro viejo (sucursal) vs.
  el nuevo (almacén) sobre el mismo `fact_inventario_snapshot` real:
  - Antes (sucursal forzada a `'Matriz Quito'`, el bug): `(0, 0)`.
  - Ahora (`almacenes_permitidos=None`, `todos_los_almacenes=True`): `(114239, 102891)`.
  - Ahora (`almacenes_permitidos=['08']`, un solo almacén asignado, SALCEDO):
    `(8160, 7285)` -- confirma que la restricción por almacén sigue funcionando
    correctamente (intersección real, no "todo por defecto").

**Nota:** `sucursal` se conserva sin cambios como dimensión **voluntaria** de
exploración para gerencia/administrador en `analytics.py`/`goals.py`/`ai-summary`
(roles ya privilegiados, `resolve_sucursal_filter(allow_override=True)` les deja
elegir o ver todo) -- el hallazgo y la corrección son específicos al uso de `sucursal`
como **mecanismo de RLS forzado** sobre roles no privilegiados (`ventas` en B-3,
`bodega` aquí), no una prohibición total de la columna/dimensión en el sistema.

## Resumen de recomendaciones por prioridad

| Prioridad | Recomendación | Estado |
|---|---|---|
| Alta | RLS real por bodega (H-1) | **Aplicado** en Fase 1 |
| Alta | Retirar `sucursal` como RLS de Bodega (blackout total confirmado) | **Aplicado** (Hallazgo Bodega-sucursal) |
| Media | `BodegaFilterBar` filtrado por bodegas asignadas | **Aplicado** en Fase 1 (ampliación) |
| Media | Icono de calendario visible + filtro inteligente categoría→proveedor | **Aplicado** en Fase 2 (parcial) |
| Media | KPIs de Gerencia filtrables por vendedor (§3.1) | **Aplicado** en Fase 3 |
| Media | Gráficos de predicción, metas/comisiones y paneles de rendimiento (§3.2-3.4) | **Verificado sin hallazgos** en Fase 3 |
| Baja | `ComboboxField` + auditoría A-0.4 de modelos (§2.3-2.4) | Pendiente (Fase 2) |
| Baja | Borrado permanente de usuarios de prueba | Pendiente (Fase 5) |
